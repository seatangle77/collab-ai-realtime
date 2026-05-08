import { computeInfoGain } from '../src/skills/perception/info-gain';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetTranscriptsInWindow = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;
const mockGetHistoricalWindowMetricsKeywords =
  queries.getHistoricalWindowMetricsKeywords as jest.MockedFunction<
    typeof queries.getHistoricalWindowMetricsKeywords
  >;
const mockWriteWindowMetricsKeywords = queries.writeWindowMetricsKeywords as jest.MockedFunction<
  typeof queries.writeWindowMetricsKeywords
>;
const mockExtractKeywordsBroad = nlp.extractKeywordsBroad as jest.MockedFunction<
  typeof nlp.extractKeywordsBroad
>;
const mockEmbed = nlp.embed as jest.MockedFunction<typeof nlp.embed>;
const mockSimilarity = nlp.similarity as jest.MockedFunction<typeof nlp.similarity>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END = new Date('2024-01-01T10:02:00Z');

function makeTranscript(userId: string, text: string) {
  return {
    transcript_id: 'tr_x',
    user_id: userId,
    speaker_name: null,
    text,
    start: WIN_START,
    end: WIN_END,
    duration: 10,
  };
}

describe('computeInfoGain', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockGetTranscriptsInWindow.mockResolvedValue([]);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([]);
    mockWriteWindowMetricsKeywords.mockResolvedValue(undefined);
    mockExtractKeywordsBroad.mockResolvedValue([]);
  });

  it('当前窗口无发言：所有用户 info_gain = null', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBeNull();
    expect(infoGains['u2']).toBeNull();
    expect(mockExtractKeywordsBroad).not.toHaveBeenCalled();
    expect(mockEmbed).not.toHaveBeenCalled();
    expect(mockWriteWindowMetricsKeywords).not.toHaveBeenCalled();
  });

  it('当前窗口提不出关键词：所有用户 info_gain = null', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '一些内容'),
      makeTranscript('u2', '另一些内容'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue([]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBeNull();
    expect(infoGains['u2']).toBeNull();
    expect(mockEmbed).not.toHaveBeenCalled();
    expect(mockWriteWindowMetricsKeywords).not.toHaveBeenCalled();
  });

  it('第一个窗口（无历史）：info_gain = null，并写入本轮关键词', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '人工智能技术很重要'),
      makeTranscript('u2', '机器学习是核心'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['人工智能', '机器学习']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBeNull();
    expect(infoGains['u2']).toBeNull();
    expect(mockEmbed).not.toHaveBeenCalled();
    expect(mockWriteWindowMetricsKeywords).toHaveBeenCalledWith(SESSION, 'u1', WIN_START, ['人工智能', '机器学习']);
    expect(mockWriteWindowMetricsKeywords).toHaveBeenCalledWith(SESSION, 'u2', WIN_START, ['人工智能', '机器学习']);
  });

  it('所有关键词与历史高度相似（>= 0.75）：info_gain = 0', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '深度学习'),
      makeTranscript('u2', '神经网络'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['深度学习', '神经网络']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([
      { keyword: '人工智能' },
      { keyword: '机器学习' },
    ] as Awaited<ReturnType<typeof queries.getHistoricalWindowMetricsKeywords>>);
    mockEmbed.mockResolvedValue([[1, 0], [0, 1], [1, 0], [0, 1]]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBe(0);
    expect(infoGains['u2']).toBe(0);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('所有关键词与历史低相似（< 0.75）：info_gain = 1.0', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '新词A'),
      makeTranscript('u2', '新词B'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['新词A', '新词B']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([
      { keyword: '历史词' },
    ] as Awaited<ReturnType<typeof queries.getHistoricalWindowMetricsKeywords>>);
    mockEmbed.mockResolvedValue([[1, 0], [0, 1], [0.5, 0.5]]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBe(1.0);
    expect(infoGains['u2']).toBe(1.0);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('部分新词：info_gain = 新词数 / 总词数', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '旧概念'),
      makeTranscript('u2', '新概念'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['旧概念', '新概念']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([
      { keyword: '旧词' },
    ] as Awaited<ReturnType<typeof queries.getHistoricalWindowMetricsKeywords>>);
    mockEmbed.mockResolvedValue([[1, 0], [0, 1], [1, 0]]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBeCloseTo(0.5);
    expect(infoGains['u2']).toBeCloseTo(0.5);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('info_gain 对所有成员相同（session 级别指标）', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '关键词'),
      makeTranscript('u2', '关键词'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['关键词']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBe(infoGains['u2']);
  });

  it('边界值：相似度恰好 = 0.75，视为已覆盖', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '新词'),
      makeTranscript('u2', '补充内容'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['新词']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([
      { keyword: '旧词' },
    ] as Awaited<ReturnType<typeof queries.getHistoricalWindowMetricsKeywords>>);
    mockEmbed.mockResolvedValue([[1, 0], [0.75, Math.sqrt(1 - 0.75 ** 2)]]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBe(0);
    expect(infoGains['u2']).toBe(0);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('边界值：相似度 = 0.749，视为新词', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '新词'),
      makeTranscript('u2', '补充内容'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['新词']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([
      { keyword: '旧词' },
    ] as Awaited<ReturnType<typeof queries.getHistoricalWindowMetricsKeywords>>);
    mockEmbed.mockResolvedValue([[1, 0], [0.749, Math.sqrt(1 - 0.749 ** 2)]]);

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBe(1.0);
    expect(infoGains['u2']).toBe(1.0);
    expect(mockSimilarity).not.toHaveBeenCalled();
  });

  it('embed 失败：对应用户 info_gain = null', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      makeTranscript('u1', '当前词'),
      makeTranscript('u2', '补充内容'),
    ]);
    mockExtractKeywordsBroad.mockResolvedValue(['当前词']);
    mockGetHistoricalWindowMetricsKeywords.mockResolvedValue([
      { keyword: '历史词' },
    ] as Awaited<ReturnType<typeof queries.getHistoricalWindowMetricsKeywords>>);
    mockEmbed.mockRejectedValue(new Error('embed down'));

    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(infoGains['u1']).toBeNull();
    expect(infoGains['u2']).toBeNull();
    expect(mockSimilarity).not.toHaveBeenCalled();
  });
});
