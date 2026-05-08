import { computeSrep } from '../src/skills/perception/srep';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetTranscripts = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;
const mockEmbed = nlp.embed as jest.MockedFunction<typeof nlp.embed>;
const mockSimilarity = nlp.similarity as jest.MockedFunction<typeof nlp.similarity>;

const SESSION = 's_test';
const MEMBERS = ['u1'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z');

function makeTranscript(userId: string, text: string) {
  return { transcript_id: 'tr_x', user_id: userId, speaker_name: null, text,
           start: WIN_START, end: WIN_END, duration: 10 };
}

describe('computeSrep', () => {
  afterEach(() => jest.resetAllMocks());

  it('只有 1 条话语：srep = null（无法计算）', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '只有一句话')]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeNull();
    expect(mockEmbed).not.toHaveBeenCalled();
  });

  it('无发言：srep = null', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeNull();
  });

  it('2 条话语：srep = 唯一 pair 的本地余弦相似度', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '第一句'),
      makeTranscript('u1', '第二句'),
    ]);
    mockEmbed.mockResolvedValue([[1, 0], [0.6, 0.8]]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeCloseTo(0.6);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('3 条话语：srep = 两两全组合 pair 均值', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', 'A'),
      makeTranscript('u1', 'B'),
      makeTranscript('u1', 'C'),
    ]);
    mockEmbed.mockResolvedValue([[1, 0], [0, 1], [1, 1]]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeCloseTo((0 + Math.SQRT1_2 + Math.SQRT1_2) / 3);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('高重复度：srep 接近 1', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '我觉得这个方案很好'),
      makeTranscript('u1', '我觉得这个方案非常好'),
    ]);
    mockEmbed.mockResolvedValue([[0.9, 0.1], [0.88, 0.12]]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeGreaterThan(0.99);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('低重复度：srep 接近 0（内容多样）', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '今天讨论财务问题'),
      makeTranscript('u1', '接下来聊技术架构'),
    ]);
    mockEmbed.mockResolvedValue([[1, 0], [0, 1]]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeCloseTo(0);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('embed 抛出异常：对应用户 srep = null', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', 'A'),
      makeTranscript('u1', 'B'),
    ]);
    mockEmbed.mockRejectedValue(new Error('embed service down'));
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(sreps['u1']).toBeNull();
  });

  it('多用户批量向量化一次，再按用户本地计算，互不影响', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', 'A'),
      makeTranscript('u1', 'B'),
      makeTranscript('u2', 'C'),
      makeTranscript('u2', 'D'),
    ]);
    mockEmbed.mockResolvedValue([
      [1, 0],
      [0.6, 0.8],
      [0, 1],
      [0.953939, 0.3],
    ]);
    const { sreps } = await computeSrep(SESSION, WIN_START, WIN_END, ['u1', 'u2']);
    expect(mockEmbed).toHaveBeenCalledTimes(1);
    expect(mockEmbed).toHaveBeenCalledWith(['A', 'B', 'C', 'D']);
    expect(mockSimilarity).not.toHaveBeenCalled();
    expect(sreps['u1']).toBeCloseTo(0.6);
    expect(sreps['u2']).toBeCloseTo(0.3);
  });
});
