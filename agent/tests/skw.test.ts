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
    expect(rows[0].skw_status).toBe('computed');
    expect(rows[0].mention_count).toBe(2);
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
    expect(rows.every((row) => row.skw_status === 'computed')).toBe(true);
    expect(rows.every((row) => row.mention_count === 3)).toBe(true);
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

  it('单人提及：不调用 embed/similarity，写入提及者 vs 其余成员的 single_mention 行', async () => {
    const members3 = ['u1', 'u2', 'u3'];
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '我只提到搭子'),
      makeTranscript('u2', '我没提那个词'),
      makeTranscript('u3', '我也没提那个词'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['搭子'],
      member_keyword_contexts: {
        u1: { 搭子: '我只提到搭子' },
        u2: {},
        u3: {},
      },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['搭子'], sources: { 搭子: 'tfidf' } });
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, members3);

    expect(keywords).toEqual(['搭子']);
    expect(mockEmbed).not.toHaveBeenCalled();
    expect(mockSimilarity).not.toHaveBeenCalled();
    expect(mockWriteKeywordSkw).toHaveBeenCalledTimes(1);

    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows).toHaveLength(2);
    expect(rows).toEqual(expect.arrayContaining([
      expect.objectContaining({
        keyword: '搭子',
        user_a_id: 'u1',
        user_b_id: 'u2',
        skw_score: 0.1,
        skw_status: 'single_mention',
        mention_count: 1,
      }),
      expect.objectContaining({
        keyword: '搭子',
        user_a_id: 'u1',
        user_b_id: 'u3',
        skw_score: 0.1,
        skw_status: 'single_mention',
        mention_count: 1,
      }),
    ]));

    expect(scores['搭子']['u1']['u2']).toBeCloseTo(0.1);
    expect(scores['搭子']['u2']['u1']).toBeCloseTo(0.1);
    expect(scores['搭子']['u1']['u3']).toBeCloseTo(0.1);
    expect(scores['搭子']['u3']['u1']).toBeCloseTo(0.1);
  });

  it('混合场景：single_mention 与 computed 关键词可同时写入，embed 只用于 computed', async () => {
    const members3 = ['u1', 'u2', 'u3'];
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '我喜欢搭子，也聊兴趣'),
      makeTranscript('u2', '我主要聊兴趣'),
      makeTranscript('u3', '我没有提到这两个关键词'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['搭子', '兴趣'],
      member_keyword_contexts: {
        u1: { 搭子: '我喜欢搭子', 兴趣: '也聊兴趣' },
        u2: { 兴趣: '我主要聊兴趣' },
        u3: {},
      },
    });
    mockCandidateRecall.mockResolvedValue({
      keywords: ['搭子', '兴趣'],
      sources: { 搭子: 'tfidf', 兴趣: 'tfidf' },
    });
    mockEmbed.mockResolvedValue([[1, 0], [0.7, 0.3]]);
    mockSimilarity.mockResolvedValue([0.66]);
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, members3);

    expect(mockEmbed).toHaveBeenCalledTimes(1);
    expect(mockSimilarity).toHaveBeenCalledTimes(1);

    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows).toEqual(expect.arrayContaining([
      expect.objectContaining({
        keyword: '搭子',
        skw_status: 'single_mention',
        skw_score: 0.1,
        mention_count: 1,
      }),
      expect.objectContaining({
        keyword: '兴趣',
        skw_status: 'computed',
        skw_score: 0.66,
        mention_count: 2,
      }),
    ]));

    expect(scores['搭子']['u1']['u2']).toBeCloseTo(0.1);
    expect(scores['兴趣']['u1']['u2']).toBeCloseTo(0.66);
  });

  it('候选词无人命中上下文：跳过，不写 DB，不进 scores', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '这里没有相关内容'),
      makeTranscript('u2', '这里也没有'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['AI'],
      member_keyword_contexts: {
        u1: {},
        u2: {},
      },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['AI'], sources: { AI: 'tfidf' } });
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(keywords).toEqual(['AI']);
    expect(scores).toEqual({ AI: {} });
    expect(mockWriteKeywordSkw).toHaveBeenCalledWith([]);
    expect(mockEmbed).not.toHaveBeenCalled();
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('所有候选词都只有 1 人提及：每词写入提及者对其他成员的 pair，且不调用 embed', async () => {
    const members3 = ['u1', 'u2', 'u3'];
    const keywords = Array.from({ length: 15 }, (_, i) => `词${i + 1}`);
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', keywords.join(' ')),
      makeTranscript('u2', '其他内容'),
      makeTranscript('u3', '更多其他内容'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords,
      member_keyword_contexts: Object.fromEntries(
        members3.map((uid) => [uid, uid === 'u1'
          ? Object.fromEntries(keywords.map((kw) => [kw, `${kw} 只在 u1 出现`]))
          : {}]),
      ) as Record<string, Record<string, string>>,
    });
    mockCandidateRecall.mockResolvedValue({
      keywords,
      sources: Object.fromEntries(keywords.map((kw) => [kw, 'tfidf'])),
    });
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    await computeSkw(SESSION, WIN_START, WIN_END, members3);

    expect(mockEmbed).not.toHaveBeenCalled();
    expect(mockSimilarity).not.toHaveBeenCalled();
    expect(mockWriteKeywordSkw).toHaveBeenCalledTimes(1);
    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows).toHaveLength(30);
    expect(rows.every((row) => row.skw_status === 'single_mention')).toBe(true);
    expect(rows.every((row) => row.skw_score === 0.1)).toBe(true);
    expect(rows.every((row) => row.mention_count === 1)).toBe(true);
  });

  it('三人场景下某词仅 u1 提及：写入 u1-u2 与 u1-u3 两条对称可回读记录', async () => {
    const members3 = ['u1', 'u2', 'u3'];
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '搭子'),
      makeTranscript('u2', '完全无关'),
      makeTranscript('u3', '也是无关'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['搭子'],
      member_keyword_contexts: {
        u1: { 搭子: '搭子' },
        u2: {},
        u3: {},
      },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['搭子'], sources: { 搭子: 'tfidf' } });
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, members3);

    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows).toEqual(expect.arrayContaining([
      expect.objectContaining({ user_a_id: 'u1', user_b_id: 'u2', skw_score: 0.1 }),
      expect.objectContaining({ user_a_id: 'u1', user_b_id: 'u3', skw_score: 0.1 }),
    ]));
    expect(scores['搭子']['u2']['u1']).toBeCloseTo(0.1);
    expect(scores['搭子']['u3']['u1']).toBeCloseTo(0.1);
  });

  it('computed 行写入时包含 skw_status 与 mention_count 新字段', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '话题A'),
      makeTranscript('u2', '话题B'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['话题'],
      member_keyword_contexts: { u1: { 话题: '话题A' }, u2: { 话题: '话题B' } },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['话题'], sources: { 话题: 'tfidf' } });
    mockEmbed.mockResolvedValue([[1, 0], [0.5, 0.5]]);
    mockSimilarity.mockResolvedValue([0.65]);
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

    const rows = mockWriteKeywordSkw.mock.calls[0][0];
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual(expect.objectContaining({
      keyword: '话题',
      user_a_id: 'u1',
      user_b_id: 'u2',
      skw_score: 0.65,
      skw_status: 'computed',
      mention_count: 2,
    }));
  });

  it('writeKeywordSkw 接收到空数组时也应保持兼容，不抛出 DB 异常', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '这里没有相关内容'),
      makeTranscript('u2', '这里也没有'),
    ]);
    mockTfidf.mockResolvedValue({
      keywords: ['AI'],
      member_keyword_contexts: {
        u1: {},
        u2: {},
      },
    });
    mockCandidateRecall.mockResolvedValue({ keywords: ['AI'], sources: { AI: 'tfidf' } });
    mockWriteKeywordSkw.mockResolvedValue(undefined);

    await expect(computeSkw(SESSION, WIN_START, WIN_END, MEMBERS)).resolves.toBeDefined();
    expect(mockWriteKeywordSkw).toHaveBeenCalledWith([]);
  });
});
