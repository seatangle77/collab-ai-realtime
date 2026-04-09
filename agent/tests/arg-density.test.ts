import { computeArgDensity } from '../src/skills/perception/arg-density';
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
  return { transcript_id: 'tr_x', user_id: userId, speaker_name: null, text,
           start: WIN_START, end: WIN_END, duration: 10 };
}

function makeSegmentResult(argDensity: number) {
  return { tokens: [], token_count: 10, unique_count: 8, ttr: 0.8, arg_density: argDensity };
}

describe('computeArgDensity', () => {
  afterEach(() => jest.resetAllMocks());

  it('正常计算：返回 NLP segment 的 arg_density 值', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '因为天气好所以出门')]);
    mockSegment.mockResolvedValue(makeSegmentResult(0.3));
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(argDensities['u1']).toBeCloseTo(0.3);
  });

  it('无发言：arg_density = null', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(argDensities['u1']).toBeNull();
    expect(argDensities['u2']).toBeNull();
    expect(mockSegment).not.toHaveBeenCalled();
  });

  it('边界值：arg_density = 0（无论证词）', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '今天天气很好')]);
    mockSegment.mockResolvedValue(makeSegmentResult(0));
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, ['u1']);
    expect(argDensities['u1']).toBe(0);
  });

  it('边界值：arg_density = 1（全是论证词）', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '因为所以因此由于')]);
    mockSegment.mockResolvedValue(makeSegmentResult(1));
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, ['u1']);
    expect(argDensities['u1']).toBe(1);
  });

  it('NLP 失败：对应用户置 null', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', '发言内容')]);
    mockSegment.mockRejectedValue(new Error('timeout'));
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, ['u1']);
    expect(argDensities['u1']).toBeNull();
  });

  it('只有空白字符的文本：不调用 NLP，置 null', async () => {
    mockGetTranscripts.mockResolvedValue([
      { transcript_id: 'tr_x', user_id: 'u1', speaker_name: null, text: '   ',
        start: WIN_START, end: WIN_END, duration: 5 },
    ]);
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, ['u1']);
    expect(argDensities['u1']).toBeNull();
    expect(mockSegment).not.toHaveBeenCalled();
  });

  it('多用户：部分失败不影响其他', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '因为如此所以这样'),
      makeTranscript('u2', '另一段'),
    ]);
    mockSegment
      .mockResolvedValueOnce(makeSegmentResult(0.4))
      .mockRejectedValueOnce(new Error('NLP error'));
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(argDensities['u1']).toBeCloseTo(0.4);
    expect(argDensities['u2']).toBeNull();
  });

  it('text 为 null 的转写记录跳过', async () => {
    mockGetTranscripts.mockResolvedValue([
      { transcript_id: 'tr_x', user_id: 'u1', speaker_name: null, text: null,
        start: WIN_START, end: WIN_END, duration: 5 },
    ]);
    const { argDensities } = await computeArgDensity(SESSION, WIN_START, WIN_END, ['u1']);
    expect(argDensities['u1']).toBeNull();
  });
});
