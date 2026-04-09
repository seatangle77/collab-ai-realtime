import { runActionLayer } from '../src/skills/run-action-layer';
import * as queries from '../src/db/queries';
import * as nlpClient from '../src/http/nlp-client';
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

const mockWritePushQueueItem = queries.writePushQueueItem as jest.MockedFunction<typeof queries.writePushQueueItem>;
const mockWriteInfoGapButton = queries.writeInfoGapButton as jest.MockedFunction<typeof queries.writeInfoGapButton>;
const mockGeneratePushBatchAnalysis = nlpClient.generatePushBatchAnalysis as jest.MockedFunction<typeof nlpClient.generatePushBatchAnalysis>;
const mockNotifyGroupSilence = nlpClient.notifyGroupSilence as jest.MockedFunction<typeof nlpClient.notifyGroupSilence>;
const mockEmbed = nlpClient.embed as jest.MockedFunction<typeof nlpClient.embed>;

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
  ],
};

describe('行动层：队列写入', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWritePushQueueItem.mockResolvedValue('pq_mock');
    mockWriteInfoGapButton.mockResolvedValue(null);
    mockEmbed.mockResolvedValue([[0.1, 0.2, 0.3]]);
    mockNotifyGroupSilence.mockResolvedValue(true);
    mockGeneratePushBatchAnalysis.mockResolvedValue([
      {
        user_id: 'uA',
        challenge_type: 'personal_stagnation',
        needs_prompt: true,
        analysis: '分析结果',
        content: '这是一条测试推送文案',
      },
    ]);
  });

  it('普通触发生成后写入 push_queue', async () => {
    await runActionLayer({
      ...BASE_PARAMS,
      triggers: [makeTrigger({})],
    });

    expect(mockGeneratePushBatchAnalysis).toHaveBeenCalledTimes(1);
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
  });
});

describe('行动层：优先级', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWritePushQueueItem.mockResolvedValue('pq_mock');
    mockWriteInfoGapButton.mockResolvedValue(null);
    mockEmbed.mockResolvedValue([[0.1, 0.2, 0.3]]);
    mockNotifyGroupSilence.mockResolvedValue(true);
    mockGeneratePushBatchAnalysis.mockResolvedValue([]);
  });

  it('group_silence + shallow_discussion 同时触发时，优先发群组提醒并跳过个人推送', async () => {
    const triggers: Trigger[] = [
      { type: 'group_silence', targetUsers: MEMBERS, triggerMetrics: { silence_s: 35 } },
      { type: 'shallow_discussion', userId: 'uA', targetUsers: ['uA'], triggerMetrics: { description: 'TTR偏低' } },
    ];

    await runActionLayer({ ...BASE_PARAMS, triggers });

    expect(mockNotifyGroupSilence).toHaveBeenCalledTimes(1);
    expect(mockGeneratePushBatchAnalysis).not.toHaveBeenCalled();
    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
  });
});

describe('行动层：info_gap 不入队', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWritePushQueueItem.mockResolvedValue('pq_mock');
    mockWriteInfoGapButton.mockResolvedValue(null);
    mockEmbed.mockResolvedValue([[0.1, 0.2, 0.3]]);
    mockNotifyGroupSilence.mockResolvedValue(true);
    mockGeneratePushBatchAnalysis.mockResolvedValue([]);
  });

  it('info_gap 触发时写按钮，普通推送逻辑不受影响', async () => {
    const triggers: Trigger[] = [
      {
        type: 'info_gap',
        keyword: '资源',
        skwScore: 0.21,
        targetUsers: ['uC'],
        triggerMetrics: { keyword: '资源' },
      },
      makeTrigger({ type: 'low_participation' }),
    ];

    await runActionLayer({ ...BASE_PARAMS, triggers });

    expect(mockWriteInfoGapButton).toHaveBeenCalledWith(
      expect.objectContaining({ user_id: 'uC', keyword: '资源' }),
    );
    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
  });
});
