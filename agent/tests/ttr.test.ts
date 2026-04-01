import { computeTtr } from '../src/skills/perception/ttr';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetTranscripts = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;
const mockSegment = nlp.segment as jest.MockedFunction<typeof nlp.segment>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z');

function makeTranscript(userId: string, text: string) {
  return { transcript_id: 'tr_x', user_id: userId, text,
           start: WIN_START, end: WIN_END, duration: 10 };
}

function makeSegmentResult(ttr: number) {
  return { tokens: [], token_count: 10, unique_count: Math.round(ttr * 10), ttr, arg_density: 0 };
}

describe('computeTtr', () => {
  afterEach(() => jest.resetAllMocks());

  it('正常计算：返回 NLP segment 的 ttr 值', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '今天天气真好')]);
    mockSegment.mockResolvedValue(makeSegmentResult(0.8));
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ttrs['u1']).toBeCloseTo(0.8);
  });

  it('无发言用户：ttr = null', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '有发言')]);
    mockSegment.mockResolvedValue(makeSegmentResult(0.6));
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ttrs['u2']).toBeNull();
  });

  it('所有用户无发言：全部 null', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ttrs['u1']).toBeNull();
    expect(ttrs['u2']).toBeNull();
    expect(mockSegment).not.toHaveBeenCalled();
  });

  it('NLP 调用失败：对应用户 ttr = null，不影响其他用户', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '正常发言'),
      makeTranscript('u2', '另一段发言'),
    ]);
    mockSegment
      .mockResolvedValueOnce(makeSegmentResult(0.7))
      .mockRejectedValueOnce(new Error('NLP timeout'));
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ttrs['u1']).toBeCloseTo(0.7);
    expect(ttrs['u2']).toBeNull();
  });

  it('多段发言合并后送 segment', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '第一段'),
      makeTranscript('u1', '第二段'),
    ]);
    mockSegment.mockResolvedValue(makeSegmentResult(0.5));
    await computeTtr(SESSION, WIN_START, WIN_END, ['u1']);
    expect(mockSegment).toHaveBeenCalledWith('第一段 第二段');
  });

  it('边界值：ttr = 1.0（每个词都不重复）', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '苹果 香蕉 橘子')]);
    mockSegment.mockResolvedValue(makeSegmentResult(1.0));
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, ['u1']);
    expect(ttrs['u1']).toBe(1.0);
  });

  it('边界值：ttr = 0（segment 返回 0，极端退化情况）', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '的的的的的')]);
    mockSegment.mockResolvedValue(makeSegmentResult(0));
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, ['u1']);
    expect(ttrs['u1']).toBe(0);
  });

  it('text 为空字符串的记录不参与合并', async () => {
    mockGetTranscripts.mockResolvedValue([
      { transcript_id: 'tr_x', user_id: 'u1', text: '',
        start: WIN_START, end: WIN_END, duration: 5 },
    ]);
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, ['u1']);
    expect(ttrs['u1']).toBeNull();
    expect(mockSegment).not.toHaveBeenCalled();
  });

  it('三名用户各自独立计算，互不影响', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '用户一的发言'),
      makeTranscript('u2', '用户二的发言'),
      makeTranscript('u3', '用户三的发言'),
    ]);
    mockSegment
      .mockResolvedValueOnce(makeSegmentResult(0.9))
      .mockResolvedValueOnce(makeSegmentResult(0.5))
      .mockResolvedValueOnce(makeSegmentResult(0.3));
    const { ttrs } = await computeTtr(SESSION, WIN_START, WIN_END, ['u1', 'u2', 'u3']);
    expect(ttrs['u1']).toBeCloseTo(0.9);
    expect(ttrs['u2']).toBeCloseTo(0.5);
    expect(ttrs['u3']).toBeCloseTo(0.3);
  });
});
