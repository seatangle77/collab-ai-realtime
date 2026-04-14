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
          text: '我对MVP不太懂',
        },
      },
    ]);
    mockValidateStructuredAnchor.mockReturnValue({
      transcriptId: 't2',
      speakerId: 'uC',
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

    await runActionLayer({ ...BASE_PARAMS, triggers });

    expect(mockNotifyGroupSilence).toHaveBeenCalledTimes(1);
    expect(mockGeneratePushContent).not.toHaveBeenCalled();
    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
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
            text: '我对MVP不太懂',
          },
        }),
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
  });

  it('info_gap: assess 通过 + 频控通过时，写按钮并通知，且写入 llm 元数据', async () => {
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
    expect(mockAssessGap).toHaveBeenCalledTimes(1);
    expect(mockWriteInfoGapButton).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        user_id: 'uC',
        keyword: 'MVP',
        gap_type: '缩写不懂',
        confidence: 0.86,
        llm_reason: '该成员明确表示不理解缩写',
      }),
    );
    expect(mockNotifyInfoGapButton).toHaveBeenCalledTimes(1);
  });

  it('info_gap: confidence 不足或无 target_user_id 时应跳过', async () => {
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

    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
    expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
  });

  it('info_gap: 命中同词 pending / 最近点击 / pending 上限 任一规则时跳过', async () => {
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
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();

    mockHasPendingKeyword.mockResolvedValue(false);
    mockHasClickedRecent.mockResolvedValue(true);
    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();

    mockHasClickedRecent.mockResolvedValue(false);
    mockGetPendingCount.mockResolvedValue(3);
    await runActionLayer({ ...BASE_PARAMS, triggers: [infoGap] });
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
  });
});
