import { runActionLayer } from '../src/skills/run-action-layer';
import * as queries from '../src/db/queries';
import * as nlpClient from '../src/http/nlp-client';
import * as pushContentSkill from '../src/skills/generate-push-content';
import type { Trigger } from '../src/skills/run-reasoning-layer';

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');
jest.mock('../src/skills/generate-push-content');

const mockWritePushQueueItem = queries.writePushQueueItem as jest.MockedFunction<typeof queries.writePushQueueItem>;
const mockWriteDiscussionState = queries.writeDiscussionState as jest.MockedFunction<typeof queries.writeDiscussionState>;
const mockWriteAiPushAnalysis = queries.writeAiPushAnalysis as jest.MockedFunction<typeof queries.writeAiPushAnalysis>;
const mockWriteInfoGapButton = queries.writeInfoGapButton as jest.MockedFunction<typeof queries.writeInfoGapButton>;
const mockDismissPendingBeforeWindow = queries.dismissPendingInfoGapButtonsBeforeWindow as jest.MockedFunction<
  typeof queries.dismissPendingInfoGapButtonsBeforeWindow
>;
const mockHasPendingKeyword = queries.hasPendingInfoGapKeyword as jest.MockedFunction<typeof queries.hasPendingInfoGapKeyword>;
const mockHasClickedRecent = queries.hasClickedInfoGapKeywordInRecentWindows as jest.MockedFunction<
  typeof queries.hasClickedInfoGapKeywordInRecentWindows
>;
const mockGetPendingCount = queries.getPendingInfoGapButtonCount as jest.MockedFunction<
  typeof queries.getPendingInfoGapButtonCount
>;
const mockAssessGap = nlpClient.assessGap as jest.MockedFunction<typeof nlpClient.assessGap>;
const mockNotifyGroupSilence = nlpClient.notifyGroupSilence as jest.MockedFunction<typeof nlpClient.notifyGroupSilence>;
const mockNotifyInfoGapButton = nlpClient.notifyInfoGapButton as jest.MockedFunction<typeof nlpClient.notifyInfoGapButton>;
const mockEmbed = nlpClient.embed as jest.MockedFunction<typeof nlpClient.embed>;
const mockGeneratePushContent = pushContentSkill.generatePushContent as jest.MockedFunction<
  typeof pushContentSkill.generatePushContent
>;
const mockValidateStructuredAnchor = pushContentSkill.validateStructuredAnchor as jest.MockedFunction<
  typeof pushContentSkill.validateStructuredAnchor
>;

const SESSION = 's_test';
const MEMBERS = ['uA', 'uB', 'uC'];
const WINDOW_START = new Date('2024-01-01T10:00:00Z');

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
  transcripts: [
    {
      transcript_id: 't1',
      user_id: 'uA',
      speaker_name: '成员A',
      text: '发言内容',
      start: new Date(),
      end: new Date(),
      duration: 5,
    },
    {
      transcript_id: 't2',
      user_id: 'uC',
      speaker_name: '成员C',
      text: '我对MVP不太懂',
      start: new Date(),
      end: new Date(),
      duration: 4,
    },
  ],
};

describe('runActionLayer (new info-gap flow)', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWritePushQueueItem.mockResolvedValue('pq_mock');
    mockWriteDiscussionState.mockResolvedValue('ds_mock');
    mockWriteAiPushAnalysis.mockResolvedValue(undefined);
    mockWriteInfoGapButton.mockResolvedValue('igb_mock');
    mockDismissPendingBeforeWindow.mockResolvedValue(0);
    mockHasPendingKeyword.mockResolvedValue(false);
    mockHasClickedRecent.mockResolvedValue(false);
    mockGetPendingCount.mockResolvedValue(0);
    mockEmbed.mockResolvedValue([[0.1, 0.2, 0.3]]);
    mockNotifyGroupSilence.mockResolvedValue(true);
    mockNotifyInfoGapButton.mockResolvedValue(undefined);
    mockAssessGap.mockResolvedValue([]);
    mockGeneratePushContent.mockResolvedValue([
      {
        targetUserId: 'uA',
        triggerType: 'low_participation',
        content: '这是一条测试推送文案',
        needsPrompt: true,
        anchor: {
          transcriptId: 't2',
          speakerId: 'uC',
          speakerName: '成员C',
          text: '我对MVP不太懂',
        },
      },
    ]);
    mockValidateStructuredAnchor.mockReturnValue({
      transcriptId: 't2',
      speakerId: 'uC',
      speakerName: '成员C',
      text: '我对MVP不太懂',
    });
  });

  it('无触发：不写队列、不写按钮', async () => {
    await runActionLayer({ ...BASE_PARAMS, triggers: [] });
    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
  });

  it('group_silence 优先：直接广播并跳过其它推送', async () => {
    const triggers: Trigger[] = [
      { type: 'group_silence', targetUsers: MEMBERS, triggerMetrics: { silence_s: 35 } },
      { type: 'shallow_discussion', userId: 'uA', targetUsers: ['uA'], triggerMetrics: { description: 'TTR偏低' } },
    ];
    mockGeneratePushContent.mockResolvedValue(
      MEMBERS.map((uid) => ({
        targetUserId: uid,
        triggerType: 'group_silence' as const,
        content: '请大家继续讨论',
        needsPrompt: true,
        anchor: null,
      })),
    );

    await runActionLayer({ ...BASE_PARAMS, triggers });

    expect(mockNotifyGroupSilence).toHaveBeenCalledTimes(1);
    expect(mockGeneratePushContent).toHaveBeenCalledTimes(1);
    expect(mockGeneratePushContent).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: SESSION,
        memberIds: MEMBERS,
        summaryText: '当前讨论摘要',
        triggers: [
          expect.objectContaining({
            type: 'group_silence',
            targetUsers: MEMBERS,
            triggerMetrics: { silence_s: 35 },
          }),
        ],
      }),
    );
    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledTimes(MEMBERS.length);
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        state_type: 'group_silence',
        ai_needs_prompt: true,
        ai_content: '请大家继续讨论',
        drop_reason: 'passed',
      }),
    );
  });

  it('普通触发：新 skill 产出后写入 push_queue 和 discussion_states', async () => {
    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockGeneratePushContent).toHaveBeenCalledTimes(1);
    expect(mockWritePushQueueItem).toHaveBeenCalledTimes(1);
    expect(mockWritePushQueueItem).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        push_content: '这是一条测试推送文案',
        content_embedding: [0.1, 0.2, 0.3],
        analysis_window_start: WINDOW_START,
      }),
    );
    expect(mockWriteDiscussionState).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        state_type: 'low_participation',
        target_user_id: 'uA',
        window_start: WINDOW_START,
        trigger_metrics: expect.objectContaining({
          speaking_ratio: 0.08,
          queued_push_id: 'pq_mock',
          anchor: {
            transcript_id: 't2',
            speaker_id: 'uC',
            speaker_name: '成员C',
            text: '我对MVP不太懂',
          },
        }),
      }),
    );
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        ai_needs_prompt: true,
        ai_content: '这是一条测试推送文案',
        drop_reason: 'passed',
      }),
    );
  });

  it('anchor 校验失败时不应入队', async () => {
    mockValidateStructuredAnchor.mockReturnValue(null);

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        drop_reason: 'anchor_invalid',
      }),
    );
  });

  it('needsPrompt=false 时应写入 needs_prompt_false 分析记录', async () => {
    mockGeneratePushContent.mockResolvedValue([
      {
        targetUserId: 'uA',
        triggerType: 'low_participation',
        content: '这条不会发送',
        needsPrompt: false,
        anchor: null,
      },
    ]);

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        ai_needs_prompt: false,
        ai_content: '这条不会发送',
        drop_reason: 'needs_prompt_false',
      }),
    );
  });

  it('content 为空时应写入 content_empty 分析记录', async () => {
    mockGeneratePushContent.mockResolvedValue([
      {
        targetUserId: 'uA',
        triggerType: 'low_participation',
        content: '   ',
        needsPrompt: true,
        anchor: null,
      },
    ]);

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        ai_needs_prompt: true,
        ai_content: '   ',
        drop_reason: 'content_empty',
      }),
    );
  });

  it('入队失败时应写入 persist_failed 分析记录', async () => {
    mockWritePushQueueItem.mockRejectedValue(new Error('queue failed'));

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        ai_needs_prompt: true,
        ai_content: '这是一条测试推送文案',
        drop_reason: 'persist_failed',
      }),
    );
  });

  it('writeDiscussionState 失败时应写入 persist_failed 分析记录', async () => {
    mockWriteDiscussionState.mockRejectedValue(new Error('state failed'));

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'low_participation',
        ai_needs_prompt: true,
        ai_content: '这是一条测试推送文案',
        drop_reason: 'persist_failed',
      }),
    );
  });

  it('group_silence 广播失败时应逐个写入 persist_failed 分析记录', async () => {
    mockNotifyGroupSilence.mockResolvedValue(false);
    mockGeneratePushContent.mockResolvedValue(
      MEMBERS.map((uid) => ({
        targetUserId: uid,
        triggerType: 'group_silence' as const,
        content: '请大家继续讨论',
        needsPrompt: true,
        anchor: null,
      })),
    );

    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [
        { type: 'group_silence', targetUsers: MEMBERS, triggerMetrics: { silence_s: 35 } },
      ],
    });

    expect(mockWriteAiPushAnalysis).toHaveBeenCalledTimes(MEMBERS.length);
    for (const uid of MEMBERS) {
      expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          session_id: SESSION,
          target_user_id: uid,
          state_type: 'group_silence',
          ai_content: '请大家继续讨论',
          drop_reason: 'persist_failed',
        }),
      );
    }
  });

  it('info_gap: 当前 action-layer 仅处理历史按钮过期，不做评估和写按钮', async () => {
    const infoGap: Trigger = {
      type: 'info_gap',
      keyword: 'MVP',
      skwScore: 0.21,
      targetUsers: MEMBERS,
      triggerMetrics: { keyword: 'MVP' },
    };
    mockAssessGap.mockResolvedValue([
      {
        keyword: 'MVP',
        needs_prompt: true,
        target_user_id: 'uC',
        gap_type: '缩写不懂',
        confidence: 0.86,
        reason: '该成员明确表示不理解缩写',
        skw_score: 0.19,
      },
    ]);

    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });

    expect(mockDismissPendingBeforeWindow).toHaveBeenCalledTimes(1);
    expect(mockAssessGap).not.toHaveBeenCalled();
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
    expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    expect(mockGeneratePushContent).not.toHaveBeenCalled();
  });

  it('info_gap: 没有直接推送目标时应在按钮过期处理后结束', async () => {
    const infoGap: Trigger = {
      type: 'info_gap',
      keyword: 'MVP',
      skwScore: 0.21,
      targetUsers: MEMBERS,
      triggerMetrics: { keyword: 'MVP' },
    };
    mockAssessGap.mockResolvedValue([
      {
        keyword: 'MVP',
        needs_prompt: true,
        target_user_id: '',
        gap_type: '缩写不懂',
        confidence: 0.69,
        reason: '不触发',
        skw_score: 0.19,
      },
    ]);

    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });

    expect(mockDismissPendingBeforeWindow).toHaveBeenCalledTimes(1);
    expect(mockAssessGap).not.toHaveBeenCalled();
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
    expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    expect(mockGeneratePushContent).not.toHaveBeenCalled();
  });

  it('info_gap: 频控相关 mock 不影响当前 action-layer 行为', async () => {
    const infoGap: Trigger = {
      type: 'info_gap',
      keyword: 'MVP',
      skwScore: 0.21,
      targetUsers: MEMBERS,
      triggerMetrics: { keyword: 'MVP' },
    };
    mockAssessGap.mockResolvedValue([
      {
        keyword: 'MVP',
        needs_prompt: true,
        target_user_id: 'uC',
        gap_type: '缩写不懂',
        confidence: 0.9,
        reason: 'should skip',
        skw_score: 0.2,
      },
    ]);
    mockHasPendingKeyword.mockResolvedValue(true);

    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });
    expect(mockDismissPendingBeforeWindow).toHaveBeenCalledTimes(1);
    expect(mockAssessGap).not.toHaveBeenCalled();
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();

    mockHasPendingKeyword.mockResolvedValue(false);
    mockHasClickedRecent.mockResolvedValue(true);
    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();

    mockHasClickedRecent.mockResolvedValue(false);
    mockGetPendingCount.mockResolvedValue(3);
    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
    expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    expect(mockGeneratePushContent).not.toHaveBeenCalled();
  });
});
