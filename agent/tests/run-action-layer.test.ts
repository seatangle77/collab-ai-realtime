import { runActionLayer } from '../src/skills/run-action-layer';
import * as queries from '../src/db/queries';
import * as nlpClient from '../src/http/nlp-client';
import type { Trigger } from '../src/skills/run-reasoning-layer';

// ── Mock ──────────────────────────────────────────────────────────────────────

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetStateCooldown    = queries.getStateCooldownUntil as jest.MockedFunction<typeof queries.getStateCooldownUntil>;
const mockGetLastPushForUser  = queries.getLastPushTimeForUser as jest.MockedFunction<typeof queries.getLastPushTimeForUser>;
const mockWriteDiscState      = queries.writeDiscussionState as jest.MockedFunction<typeof queries.writeDiscussionState>;
const mockWritePushLog        = queries.writePushLog as jest.MockedFunction<typeof queries.writePushLog>;
const mockWriteInfoGapButton  = queries.writeInfoGapButton as jest.MockedFunction<typeof queries.writeInfoGapButton>;
const mockGeneratePush        = nlpClient.generatePush as jest.MockedFunction<typeof nlpClient.generatePush>;

// ── 基础数据 ──────────────────────────────────────────────────────────────────

const SESSION     = 's_test';
const MEMBERS     = ['uA', 'uB', 'uC'];
const WINDOW_START = new Date('2024-01-01T10:00:00Z');

const PAST   = new Date(Date.now() - 300_000);   // 5分钟前（冷却已过）
const FUTURE = new Date(Date.now() + 200_000);   // 未来（冷却中）
const RECENT = new Date(Date.now() - 50_000);    // 50秒前（跨状态冷却内）

function makeTrigger(overrides: Partial<Trigger>): Trigger {
  return {
    type: 'low_participation',
    userId: 'uA',
    targetUsers: ['uA'],
    triggerMetrics: { speaking_ratio: 0.08 },
    ...overrides,
  };
}

const BASE_PARAMS = {
  sessionId: SESSION,
  windowStart: WINDOW_START,
  memberIds: MEMBERS,
  summaryText: '当前讨论摘要',
  transcripts: [{ transcript_id: 't1', user_id: 'uA', text: '发言内容', start: new Date(), end: new Date(), duration: 5 }],
};

// ── 测试 ──────────────────────────────────────────────────────────────────────

describe('行动层：冷却', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWriteDiscState.mockResolvedValue('ds_mock');
    mockWritePushLog.mockResolvedValue(undefined);
    mockWriteInfoGapButton.mockResolvedValue(undefined);
    mockGeneratePush.mockResolvedValue('这是一条测试推送文案');
  });

  it('单状态冷却中 → 不写 push_logs', async () => {
    mockGetStateCooldown.mockResolvedValue(FUTURE);   // 冷却未过
    mockGetLastPushForUser.mockResolvedValue(PAST);

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWritePushLog).not.toHaveBeenCalled();
  });

  it('跨状态冷却中（50s 内已推） → 不写 push_logs', async () => {
    mockGetStateCooldown.mockResolvedValue(null);     // 单状态冷却已过
    mockGetLastPushForUser.mockResolvedValue(RECENT); // 50s 前刚推过

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWritePushLog).not.toHaveBeenCalled();
  });

  it('两个冷却均已过 → 调 generatePush 并写 push_logs', async () => {
    mockGetStateCooldown.mockResolvedValue(null);
    mockGetLastPushForUser.mockResolvedValue(PAST);

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockGeneratePush).toHaveBeenCalledTimes(1);
    expect(mockWritePushLog).toHaveBeenCalledTimes(1);
    expect(mockWritePushLog).toHaveBeenCalledWith(
      expect.objectContaining({ target_user_id: 'uA', push_channel: 'glasses' }),
    );
  });
});

describe('行动层：优先级', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWriteDiscState.mockResolvedValue('ds_mock');
    mockWritePushLog.mockResolvedValue(undefined);
    mockWriteInfoGapButton.mockResolvedValue(undefined);
    mockGeneratePush.mockResolvedValue('测试文案');
  });

  it('group_silence + shallow_discussion 同时触发 → group_silence 先推，跨状态冷却阻断 shallow_discussion', async () => {
    // group_silence 对全组推送后，uA 的跨状态冷却被设置
    // shallow_discussion 对 uA 触发时，getLastPushTimeForUser 返回刚才那次推送
    let pushCount = 0;
    mockGetStateCooldown.mockResolvedValue(null);
    mockGetLastPushForUser.mockImplementation(async () => {
      // 第一次调用（group_silence 处理 uA）：无记录，通过
      // 第二次调用（shallow_discussion 处理 uA）：模拟刚被推过，阻断
      pushCount++;
      return pushCount <= MEMBERS.length ? null : RECENT;
    });

    const triggers: Trigger[] = [
      { type: 'group_silence',      targetUsers: MEMBERS, triggerMetrics: { silence_s: 35 } },
      { type: 'shallow_discussion', userId: 'uA', targetUsers: ['uA'], triggerMetrics: { description: 'TTR偏低' } },
    ];

    await runActionLayer({ ...BASE_PARAMS, triggers });

    // group_silence 推了3条（全组），shallow_discussion 被跨状态冷却阻断
    expect(mockWritePushLog).toHaveBeenCalledTimes(MEMBERS.length);
    const channels = (mockWritePushLog.mock.calls as Array<[{ push_channel: string }]>).map((c) => c[0].push_channel);
    expect(channels.every((ch) => ch === 'glasses')).toBe(true);
  });
});

describe('行动层：info_gap 不参与冷却', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWriteInfoGapButton.mockResolvedValue(undefined);
    mockWritePushLog.mockResolvedValue(undefined);
    mockWriteDiscState.mockResolvedValue('ds_mock');
    mockGeneratePush.mockResolvedValue('测试文案');
    // 模拟跨状态冷却中，任何普通推送都会被阻断
    mockGetStateCooldown.mockResolvedValue(FUTURE);
    mockGetLastPushForUser.mockResolvedValue(RECENT);
  });

  it('info_gap 触发时写按钮，不受冷却影响；普通触发被冷却阻断', async () => {
    const triggers: Trigger[] = [
      {
        type: 'info_gap',
        keyword: '资源',
        skwScore: 0.21,
        targetUsers: ['uC'],
        triggerMetrics: { keyword: '资源' },
      },
      makeTrigger({ type: 'low_participation' }),  // 被冷却阻断
    ];

    await runActionLayer({ ...BASE_PARAMS, triggers });

    expect(mockWriteInfoGapButton).toHaveBeenCalledWith(
      expect.objectContaining({ user_id: 'uC', keyword: '资源' }),
    );
    expect(mockWritePushLog).not.toHaveBeenCalled();
  });
});
