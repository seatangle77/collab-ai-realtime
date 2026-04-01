import { computeSilence } from '../src/skills/perception/silence';
import * as queries from '../src/db/queries';

jest.mock('../src/db/queries');
const mockGetLastSpeak = queries.getLastSpeakEndPerUser as jest.MockedFunction<
  typeof queries.getLastSpeakEndPerUser
>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z'); // 120s 窗口

describe('computeSilence', () => {
  afterEach(() => jest.resetAllMocks());

  it('用户 10s 前说完话：silence_s ≈ 10', async () => {
    const lastEnd = new Date(WIN_END.getTime() - 10_000);
    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: lastEnd }]);
    const { silenceSeconds } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(silenceSeconds['u1']).toBeCloseTo(10, 0);
  });

  it('用户在窗口内从未发言：silence_s = 120（窗口长度）', async () => {
    mockGetLastSpeak.mockResolvedValue([]);
    const { silenceSeconds } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(silenceSeconds['u1']).toBe(120);
    expect(silenceSeconds['u2']).toBe(120);
  });

  it('用户刚说完（last_end = WIN_END）：silence_s = 0', async () => {
    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: WIN_END }]);
    const { silenceSeconds } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(silenceSeconds['u1']).toBe(0);
  });

  it('边界值：silence_s 不为负数', async () => {
    // last_end 比 WIN_END 晚（时钟误差场景）
    const lastEnd = new Date(WIN_END.getTime() + 5_000);
    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: lastEnd }]);
    const { silenceSeconds } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(silenceSeconds['u1']).toBeGreaterThanOrEqual(0);
  });

  it('部分用户有记录，其余为 120s', async () => {
    const lastEnd = new Date(WIN_END.getTime() - 30_000);
    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: lastEnd }]);
    const { silenceSeconds } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(silenceSeconds['u1']).toBeCloseTo(30, 0);
    expect(silenceSeconds['u2']).toBe(120);
  });

  it('边界值：silence 恰好 = 30s（群体停滞阈值）', async () => {
    const exactly30 = new Date(WIN_END.getTime() - 30_000);
    const just29 = new Date(WIN_END.getTime() - 29_000);
    const just31 = new Date(WIN_END.getTime() - 31_000);

    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: exactly30 }]);
    const { silenceSeconds: at30 } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(at30['u1']).toBeCloseTo(30, 0);

    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: just29 }]);
    const { silenceSeconds: at29 } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(at29['u1']).toBeLessThan(30);

    mockGetLastSpeak.mockResolvedValue([{ user_id: 'u1', last_end: just31 }]);
    const { silenceSeconds: at31 } = await computeSilence(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(at31['u1']).toBeGreaterThan(30);
  });

  it('memberIds 为空：返回空对象', async () => {
    mockGetLastSpeak.mockResolvedValue([]);
    const { silenceSeconds } = await computeSilence(SESSION, WIN_START, WIN_END, []);
    expect(Object.keys(silenceSeconds)).toHaveLength(0);
  });

  it('DB 查询失败：向上抛出', async () => {
    mockGetLastSpeak.mockRejectedValue(new Error('timeout'));
    await expect(
      computeSilence(SESSION, WIN_START, WIN_END, MEMBERS),
    ).rejects.toThrow('timeout');
  });
});
