import { generateStructuredPush } from '../src/http/nlp-client';
import {
  generatePushContent,
  validateStructuredAnchor,
} from '../src/skills/generate-push-content';
import type { Trigger } from '../src/skills/run-reasoning-layer';

jest.mock('../src/http/nlp-client');

const mockGenerateStructuredPush = generateStructuredPush as jest.MockedFunction<typeof generateStructuredPush>;

const BASE_TRANSCRIPTS = [
  {
    transcript_id: 't1',
    user_id: 'uB',
    speaker_name: 'B',
    text: '我们先限定MVP范围',
    start: new Date('2024-01-01T10:00:00Z'),
    end: new Date('2024-01-01T10:00:05Z'),
    duration: 5,
  },
  {
    transcript_id: 't2',
    user_id: 'uA',
    speaker_name: 'A',
    text: '我还没想清楚',
    start: new Date('2024-01-01T10:00:06Z'),
    end: new Date('2024-01-01T10:00:08Z'),
    duration: 2,
  },
  {
    transcript_id: 't3',
    user_id: 'uC',
    speaker_name: 'C',
    text: '不如先收窄功能边界',
    start: new Date('2024-01-01T10:00:09Z'),
    end: new Date('2024-01-01T10:00:13Z'),
    duration: 4,
  },
];

function makeParams(triggers: Trigger[]) {
  return {
    sessionId: 's1',
    triggers,
    transcripts: BASE_TRANSCRIPTS,
    summaryText: '讨论围绕 MVP 范围收敛展开',
    memberIds: ['uA', 'uB', 'uC'],
  };
}

describe('generatePushContent', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockGenerateStructuredPush.mockResolvedValue({
      needs_prompt: true,
      anchor: {
        transcript_id: 't1',
        speaker_id: 'uB',
        text: '我们先限定MVP范围',
      },
      content: '你认可先限定MVP范围吗？',
    });
  });

  it('group_silence 直接返回固定文案且不调用后端', async () => {
    const items = await generatePushContent(
      makeParams([
        {
          type: 'group_silence',
          targetUsers: ['uA', 'uB'],
          triggerMetrics: { silence_s: 35 },
        },
      ]),
    );

    expect(items).toEqual([
      {
        targetUserId: 'uA',
        triggerType: 'group_silence',
        content: '小组已沉默超过30秒，大家可以继续讨论～',
        needsPrompt: true,
        anchor: null,
      },
      {
        targetUserId: 'uB',
        triggerType: 'group_silence',
        content: '小组已沉默超过30秒，大家可以继续讨论～',
        needsPrompt: true,
        anchor: null,
      },
    ]);
    expect(mockGenerateStructuredPush).not.toHaveBeenCalled();
  });

  it('shallow_discussion 会把 transcript 和指标映射到后端接口', async () => {
    const items = await generatePushContent(
      makeParams([
        {
          type: 'shallow_discussion',
          userId: 'uA',
          targetUsers: ['uA'],
          triggerMetrics: { ttr: 0.2, arg_density: 0.01 },
        },
      ]),
    );

    expect(mockGenerateStructuredPush).toHaveBeenCalledWith({
      trigger_type: 'shallow_discussion',
      summary: '讨论围绕 MVP 范围收敛展开',
      transcripts: [
        { transcript_id: 't1', user_id: 'uB', speaker_name: 'B', text: '我们先限定MVP范围' },
        { transcript_id: 't2', user_id: 'uA', speaker_name: 'A', text: '我还没想清楚' },
        { transcript_id: 't3', user_id: 'uC', speaker_name: 'C', text: '不如先收窄功能边界' },
      ],
      user_id: 'uA',
      trigger_metrics: { ttr: 0.2, arg_density: 0.01 },
      candidate_points: [],
    });
    expect(items[0]).toEqual({
      targetUserId: 'uA',
      triggerType: 'shallow_discussion',
      content: '你认可先限定MVP范围吗？',
      needsPrompt: true,
      anchor: {
        transcriptId: 't1',
        speakerId: 'uB',
        text: '我们先限定MVP范围',
      },
    });
  });

  it('shallow_discussion 缺少目标成员发言时直接跳过', async () => {
    const items = await generatePushContent({
      ...makeParams([
        {
          type: 'shallow_discussion',
          userId: 'uZ',
          targetUsers: ['uZ'],
          triggerMetrics: { ttr: 0.2 },
        },
      ]),
    });

    expect(items).toEqual([
      {
        targetUserId: 'uZ',
        triggerType: 'shallow_discussion',
        content: '',
        needsPrompt: false,
        anchor: null,
      },
    ]);
    expect(mockGenerateStructuredPush).not.toHaveBeenCalled();
  });

  it('shallow_discussion 没有可用结构化指标时直接跳过', async () => {
    const items = await generatePushContent(
      makeParams([
        {
          type: 'shallow_discussion',
          userId: 'uA',
          targetUsers: ['uA'],
          triggerMetrics: { description: 'only text' },
        },
      ]),
    );

    expect(items[0]?.needsPrompt).toBe(false);
    expect(mockGenerateStructuredPush).not.toHaveBeenCalled();
  });

  it('low_participation 会把未回应候选点传给后端接口', async () => {
    const items = await generatePushContent(
      makeParams([
        {
          type: 'low_participation',
          userId: 'uA',
          targetUsers: ['uA'],
          triggerMetrics: { speaking_ratio: 0.08 },
        },
      ]),
    );

    expect(mockGenerateStructuredPush).toHaveBeenCalledWith({
      trigger_type: 'low_participation',
      summary: '讨论围绕 MVP 范围收敛展开',
      transcripts: [
        { transcript_id: 't1', user_id: 'uB', speaker_name: 'B', text: '我们先限定MVP范围' },
        { transcript_id: 't2', user_id: 'uA', speaker_name: 'A', text: '我还没想清楚' },
        { transcript_id: 't3', user_id: 'uC', speaker_name: 'C', text: '不如先收窄功能边界' },
      ],
      user_id: 'uA',
      trigger_metrics: { speaking_ratio: 0.08 },
      candidate_points: [
        { transcript_id: 't3', speaker_id: 'uC', text: '不如先收窄功能边界' },
      ],
    });
    expect(items[0]?.triggerType).toBe('low_participation');
    expect(items[0]?.needsPrompt).toBe(true);
  });

  it('low_participation 没有候选点时直接跳过', async () => {
    const params = {
      sessionId: 's1',
      triggers: [
        {
          type: 'low_participation',
          userId: 'uA',
          targetUsers: ['uA'],
          triggerMetrics: { speaking_ratio: 0.08 },
        } satisfies Trigger,
      ],
      transcripts: [
        {
          transcript_id: 't1',
          user_id: 'uA',
          speaker_name: 'A',
          text: '我先回应一下',
          start: new Date('2024-01-01T10:00:00Z'),
          end: new Date('2024-01-01T10:00:02Z'),
          duration: 2,
        },
      ],
      summaryText: '讨论围绕 MVP 范围收敛展开',
      memberIds: ['uA', 'uB'],
    };

    const items = await generatePushContent(params);

    expect(items).toEqual([
      {
        targetUserId: 'uA',
        triggerType: 'low_participation',
        content: '',
        needsPrompt: false,
        anchor: null,
      },
    ]);
    expect(mockGenerateStructuredPush).not.toHaveBeenCalled();
  });

  it('后端返回 needs_prompt=false 时应透传为空结果', async () => {
    mockGenerateStructuredPush.mockResolvedValueOnce({
      needs_prompt: false,
      anchor: null,
      content: '',
    });

    const items = await generatePushContent(
      makeParams([
        {
          type: 'low_participation',
          userId: 'uA',
          targetUsers: ['uA'],
          triggerMetrics: { speaking_ratio: 0.08 },
        },
      ]),
    );

    expect(items[0]).toEqual({
      targetUserId: 'uA',
      triggerType: 'low_participation',
      content: '',
      needsPrompt: false,
      anchor: null,
    });
  });

  it('后端返回无效 anchor 时应降级为空结果', async () => {
    mockGenerateStructuredPush.mockResolvedValueOnce({
      needs_prompt: true,
      anchor: {
        transcript_id: '',
        speaker_id: 'uB',
        text: '我们先限定MVP范围',
      },
      content: '你认可先限定MVP范围吗？',
    });

    const items = await generatePushContent(
      makeParams([
        {
          type: 'low_participation',
          userId: 'uA',
          targetUsers: ['uA'],
          triggerMetrics: { speaking_ratio: 0.08 },
        },
      ]),
    );

    expect(items[0]?.needsPrompt).toBe(false);
    expect(items[0]?.anchor).toBeNull();
  });
});

describe('validateStructuredAnchor', () => {
  const transcripts = BASE_TRANSCRIPTS;

  it('匹配 transcript / speaker / text 时返回 anchor', () => {
    const result = validateStructuredAnchor({
      anchor: {
        transcriptId: 't1',
        speakerId: 'uB',
        text: '我们先限定MVP范围',
      },
      transcripts,
      memberIds: ['uA', 'uB', 'uC'],
    });

    expect(result).toEqual({
      transcriptId: 't1',
      speakerId: 'uB',
      text: '我们先限定MVP范围',
    });
  });

  it('speaker 不在会话成员中时返回 null', () => {
    const result = validateStructuredAnchor({
      anchor: {
        transcriptId: 't1',
        speakerId: 'uZ',
        text: '我们先限定MVP范围',
      },
      transcripts,
      memberIds: ['uA', 'uB', 'uC'],
    });

    expect(result).toBeNull();
  });

  it('anchor 文本与原始 transcript 明显不匹配时返回 null', () => {
    const result = validateStructuredAnchor({
      anchor: {
        transcriptId: 't1',
        speakerId: 'uB',
        text: '完全不同的话',
      },
      transcripts,
      memberIds: ['uA', 'uB', 'uC'],
    });

    expect(result).toBeNull();
  });
});
