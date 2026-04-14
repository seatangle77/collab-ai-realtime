import { computeSkw } from '../src/skills/perception/skw';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetTranscripts = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;
const mockWriteKeywordSkw = queries.writeKeywordSkw as jest.MockedFunction<
  typeof queries.writeKeywordSkw
>;
const mockTfidf = nlp.tfidf as jest.MockedFunction<typeof nlp.tfidf>;
const mockCandidateRecall = nlp.candidateRecall as jest.MockedFunction<typeof nlp.candidateRecall>;
const mockEmbed = nlp.embed as jest.MockedFunction<typeof nlp.embed>;
const mockSimilarity = nlp.similarity as jest.MockedFunction<typeof nlp.similarity>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z');

function makeTranscript(userId: string, text: string) {
  return { transcript_id: 'tr_x', user_id: userId, speaker_name: null, text,
           start: WIN_START, end: WIN_END, duration: 10 };
}

describe('computeSkw', () => {
  afterEach(() => jest.resetAllMocks());

  it('成员 < 2：直接返回空结果，不调用 NLP', async () => {
    const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, ['u1']);
    expect(keywords).toEqual([]);
    expect(scores).toEqual({});
    expect(mockTfidf).not.toHaveBeenCalled();
    expect(mockCandidateRecall).not.toHaveBeenCalled();
  });

  it('无人发言：返回空结果', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { keywords } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(keywords).toEqual([]);
  });

  it('正常流程：提取关键词并写入 keyword_skw', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '人工智能技术很重要'),
      makeTranscript('u2', '机器学习是核心'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['人工智能', '机器学习'],
      member_keyword_contexts: {
        u1: { '人工智能': '人工智能技术很重要', '机器学习': '机器学习是核心' },
        u2: { '人工智能': '人工智能应用很广', '机器学习': '机器学习是核心' },
      },
    });
    mockCandidateRecall.mockResolvedValue({
      keywords: ['人工智能'],
      sources: { '人工智能': 'tfidf' },
    });
    mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
    mockSimilarity.mockResolvedValue([0.75]);
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(keywords).toContain('人工智能');
    expect(mockWriteKeywordSkw).toHaveBeenCalled();
    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0].session_id).toBe(SESSION);
    expect(scores['人工智能']['u1']['u2']).toBeCloseTo(0.75);
    expect(scores['人工智能']['u2']['u1']).toBeCloseTo(0.75); // 对称
  });

  it('tfidf 返回空关键词：不写 DB', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '啊'),
      makeTranscript('u2', '嗯'),
    ]);
    mockTfidf.mockResolvedValue({ keywords: [], member_keyword_contexts: {} });
    mockCandidateRecall.mockResolvedValue({ keywords: [], sources: {} });
    const { keywords } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(keywords).toEqual([]);
    expect(mockWriteKeywordSkw).not.toHaveBeenCalled();
  });

  it('三人场景：生成 3 个 pair（u1-u2, u1-u3, u2-u3）', async () => {
    const members3 = ['u1', 'u2', 'u3'];
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '人工智能'),
      makeTranscript('u2', '机器学习'),
      makeTranscript('u3', '深度学习'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['技术'],
      member_keyword_contexts: {
        u1: { '技术': '人工智能技术' },
        u2: { '技术': '机器学习技术' },
        u3: { '技术': '深度学习技术' },
      },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['技术'], sources: { 技术: 'tfidf' } });
    mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2], [0.6, 0.4]]);
    mockSimilarity.mockResolvedValue([0.9, 0.7, 0.5]); // 3 pairs
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    await computeSkw(SESSION, WIN_START, WIN_END, members3);
    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows).toHaveLength(3); // 3 pairs for 1 keyword
  });

  it('skw_score 对称性：scores[kw][a][b] === scores[kw][b][a]', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '话题A'),
      makeTranscript('u2', '话题B'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['话题'],
      member_keyword_contexts: { u1: { '话题': '话题A' }, u2: { '话题': '话题B' } },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['话题'], sources: { 话题: 'tfidf' } });
    mockEmbed.mockResolvedValue([[1, 0], [0.5, 0.5]]);
    mockSimilarity.mockResolvedValue([0.65]);
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(scores['话题']['u1']['u2']).toBeCloseTo(0.65);
    expect(scores['话题']['u2']['u1']).toBeCloseTo(0.65);
  });

  it('只有一人有发言（另一人无文本）：不满足双人条件，返回空', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '只有我说话')]);
    const { keywords } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(keywords).toEqual([]);
    expect(mockTfidf).not.toHaveBeenCalled();
    expect(mockCandidateRecall).not.toHaveBeenCalled();
  });
});
