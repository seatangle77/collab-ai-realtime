import { computeInfoGain } from '../src/skills/perception/info-gain';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetHistoricalKeywords = queries.getHistoricalKeywords as jest.MockedFunction<
  typeof queries.getHistoricalKeywords
>;
const mockEmbed = nlp.embed as jest.MockedFunction<typeof nlp.embed>;
const mockSimilarity = nlp.similarity as jest.MockedFunction<typeof nlp.similarity>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z');

describe('computeInfoGain', () => {
  afterEach(() => jest.resetAllMocks());

  it('当前无关键词：所有用户 info_gain = null', async () => {
    const { infoGains } = await computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS, []);
    expect(infoGains['u1']).toBeNull();
    expect(infoGains['u2']).toBeNull();
    expect(mockEmbed).not.toHaveBeenCalled();
  });

  it('第一个窗口（无历史）：info_gain = 1.0', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([]);
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['人工智能', '机器学习'],
    );
    expect(infoGains['u1']).toBe(1.0);
    expect(infoGains['u2']).toBe(1.0);
    expect(mockEmbed).not.toHaveBeenCalled();
  });

  it('所有关键词与历史高度相似（≥ 0.75）：info_gain = 0', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([
      { keyword: '人工智能' }, { keyword: '机器学习' },
    ]);
    // cur=[A,B], hist=[C,D], 4个pair全部相似度 = 0.9
    mockEmbed.mockResolvedValue([[1,0],[0,1],[1,0],[0,1]]);
    mockSimilarity.mockResolvedValue([0.9, 0.9, 0.9, 0.9]);
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['深度学习', '神经网络'],
    );
    expect(infoGains['u1']).toBe(0);
  });

  it('所有关键词与历史低相似（< 0.75）：info_gain = 1.0', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([{ keyword: '历史词' }]);
    mockEmbed.mockResolvedValue([[1,0],[0,1],[0.5,0.5]]);
    mockSimilarity.mockResolvedValue([0.1, 0.2]); // 2个cur词 vs 1个hist词
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['新词A', '新词B'],
    );
    expect(infoGains['u1']).toBe(1.0);
  });

  it('部分新词：info_gain = 新词数 / 总词数', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([{ keyword: '旧词' }]);
    // cur=[A, B], hist=[C]; pair(A,C)=0.9（已覆盖），pair(B,C)=0.1（新词）
    mockEmbed.mockResolvedValue([[1,0],[0,1],[0.5,0.5]]);
    mockSimilarity.mockResolvedValue([0.9, 0.1]);
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['旧概念', '新概念'],
    );
    expect(infoGains['u1']).toBeCloseTo(0.5); // 1/2
  });

  it('info_gain 对所有成员相同（session 级别指标）', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([]);
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['关键词'],
    );
    expect(infoGains['u1']).toBe(infoGains['u2']);
  });

  it('边界值：相似度恰好 = 0.75（不满足 < 0.75，视为已覆盖）', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([{ keyword: '旧词' }]);
    mockEmbed.mockResolvedValue([[1, 0], [0.9, 0.1]]);
    mockSimilarity.mockResolvedValue([0.75]); // 恰好等于阈值，不是新词
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['新词'],
    );
    expect(infoGains['u1']).toBe(0);
  });

  it('边界值：相似度 = 0.749（< 0.75，视为新词）', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([{ keyword: '旧词' }]);
    mockEmbed.mockResolvedValue([[1, 0], [0.9, 0.1]]);
    mockSimilarity.mockResolvedValue([0.749]);
    const { infoGains } = await computeInfoGain(
      SESSION, WIN_START, WIN_END, MEMBERS, ['新词'],
    );
    expect(infoGains['u1']).toBe(1.0);
  });

  it('embed 失败：向上抛出', async () => {
    mockGetHistoricalKeywords.mockResolvedValue([{ keyword: '历史词' }]);
    mockEmbed.mockRejectedValue(new Error('embed down'));
    await expect(
      computeInfoGain(SESSION, WIN_START, WIN_END, MEMBERS, ['当前词']),
    ).rejects.toThrow('embed down');
  });
});
