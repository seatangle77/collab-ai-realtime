import { computeSpeakingRatio } from '../src/skills/perception/speaking-ratio';
import * as queries from '../src/db/queries';

jest.mock('../src/db/queries');
const mockGetTranscripts = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2', 'u3'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z'); // 120s 窗口

function makeTranscript(userId: string, durationS: number) {
  return {
    transcript_id: 'tr_x',
    user_id: userId,
    text: 'hello',
    start: WIN_START,
    end: new Date(WIN_START.getTime() + durationS * 1000),
    duration: durationS,
  };
}

describe('computeSpeakingRatio', () => {
  afterEach(() => jest.resetAllMocks());

  it('正常计算：u1 说了 60s，ratio = 0.5', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', 60)]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratios['u1']).toBeCloseTo(0.5);
    expect(ratios['u2']).toBe(0);
    expect(ratios['u3']).toBe(0);
  });

  it('多段发言累加：u2 两段各 30s，ratio = 0.5', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u2', 30),
      makeTranscript('u2', 30),
    ]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratios['u2']).toBeCloseTo(0.5);
  });

  it('窗口内无发言：所有 ratio = 0', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    for (const uid of MEMBERS) expect(ratios[uid]).toBe(0);
  });

  it('发言超过窗口长度：ratio 上限为 1', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', 200)]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratios['u1']).toBe(1);
  });

  it('duration 为 null 时用 start/end 推算', async () => {
    mockGetTranscripts.mockResolvedValue([
      { transcript_id: 'tr_x', user_id: 'u1', text: 'hi',
        start: WIN_START,
        end: new Date(WIN_START.getTime() + 60_000),
        duration: null },
    ]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratios['u1']).toBeCloseTo(0.5);
  });

  it('user_id 为 null 的记录忽略', async () => {
    mockGetTranscripts.mockResolvedValue([
      { transcript_id: 'tr_x', user_id: null, text: 'hi',
        start: WIN_START, end: WIN_END, duration: 60 },
    ]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    for (const uid of MEMBERS) expect(ratios[uid]).toBe(0);
  });

  it('三人各说不同时长，ratio 独立计算', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', 18),   // 15%
      makeTranscript('u2', 60),   // 50%
      makeTranscript('u3', 12),   // 10%
    ]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratios['u1']).toBeCloseTo(0.15);
    expect(ratios['u2']).toBeCloseTo(0.50);
    expect(ratios['u3']).toBeCloseTo(0.10);
  });

  it('边界值：ratio 恰好等于 15%（17.9999s ≈ 14.99%，18s = 15%）', async () => {
    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', 17.9)]);
    const { ratios: ratiosBelow } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratiosBelow['u1']).toBeLessThan(0.15);

    mockGetTranscripts.mockResolvedValue([makeTranscript('u1', 18)]);
    const { ratios: ratiosAt } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(ratiosAt['u1']).toBeCloseTo(0.15);
  });

  it('memberIds 为空数组：返回空 ratios', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { ratios } = await computeSpeakingRatio(SESSION, WIN_START, WIN_END, []);
    expect(Object.keys(ratios)).toHaveLength(0);
  });

  it('DB 查询抛出异常：向上抛出', async () => {
    mockGetTranscripts.mockRejectedValue(new Error('DB connection lost'));
    await expect(
      computeSpeakingRatio(SESSION, WIN_START, WIN_END, MEMBERS),
    ).rejects.toThrow('DB connection lost');
  });
});
