import { runActionLayer } from '../src/skills/run-action-layer';
import * as queries from '../src/db/queries';
import * as nlpClient from '../src/http/nlp-client';
import type { PipelineResult } from '../src/skills/run-perception-pipeline';

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

const mockDismissPendingBeforeWindow =
  queries.dismissPendingInfoGapButtonsBeforeWindow as jest.MockedFunction<
    typeof queries.dismissPendingInfoGapButtonsBeforeWindow
  >;
const mockWritePushQueueItem = queries.writePushQueueItem as jest.MockedFunction<typeof queries.writePushQueueItem>;
const mockWriteDiscussionState = queries.writeDiscussionState as jest.MockedFunction<typeof queries.writeDiscussionState>;
const mockWriteAiPushAnalysis = queries.writeAiPushAnalysis as jest.MockedFunction<typeof queries.writeAiPushAnalysis>;
const mockAnalyzeMembers = nlpClient.analyzeMembers as jest.MockedFunction<typeof nlpClient.analyzeMembers>;
const mockEmbed = nlpClient.embed as jest.MockedFunction<typeof nlpClient.embed>;

const SESSION = 's_test';
const MEMBERS = ['uA', 'uB', 'uC'];
const WINDOW_START = new Date('2024-01-01T10:00:00Z');

const PERCEPTION_RESULT: PipelineResult = {
  speakingRatios: { uA: 0.1, uB: 0.45, uC: 0.45 },
  silenceSeconds: { uA: 42, uB: 3, uC: 6 },
  ttrs: { uA: 0.31, uB: 0.66, uC: 0.58 },
  argDensities: { uA: 0.01, uB: 0.11, uC: 0.09 },
  sreps: { uA: 0.81, uB: 0.42, uC: 0.46 },
  infoGains: { uA: 0.2, uB: 0.5, uC: 0.5 },
  hasReasoningMap: { uA: false, uB: true, uC: true },
  hasEvidenceMap: { uA: false, uB: false, uC: true },
  reasoningSourceMap: {
    uA: '发言中只有观点表态，没有展开原因。',
    uB: '发言中明确说明了选择该方案的原因。',
    uC: '发言中明确说明了选择该方案的原因。',
  },
  evidenceSourceMap: {
    uA: '发言中没有提供例子、数据或事实依据。',
    uB: '发言中没有提供例子、数据或事实依据。',
    uC: '发言中引用了具体案例作为支撑。',
  },
  skwScores: {},
  keywords: [],
};

const TRANSCRIPTS = [
  {
    transcript_id: 't1',
    user_id: 'uA',
    speaker_name: '成员A',
    text: '我觉得这个方案可以。',
    start: new Date(),
    end: new Date(),
    duration: 3,
  },
  {
    transcript_id: 't2',
    user_id: 'uB',
    speaker_name: '成员B',
    text: '我们先限定 MVP 范围，因为这样成本更低。',
    start: new Date(),
    end: new Date(),
    duration: 5,
  },
];

describe('runActionLayer', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockDismissPendingBeforeWindow.mockResolvedValue(0);
    mockWritePushQueueItem.mockResolvedValue('pq_1');
    mockWriteDiscussionState.mockResolvedValue('ds_1');
    mockWriteAiPushAnalysis.mockResolvedValue(undefined);
    mockEmbed.mockResolvedValue([[0.1, 0.2, 0.3]]);
    mockAnalyzeMembers.mockResolvedValue([
      {
        user_id: 'uA',
        challenge_type: 'stagnation',
        needs_prompt: true,
        analysis: 'uA 参与不足，且本轮缺少理由和依据。',
        content: '你可以先说说你最担心的是哪一点。',
        anchor: {
          transcript_id: 't1',
          speaker_id: 'uA',
          speaker_name: '成员A',
          text: '我觉得这个方案可以。',
        },
      },
    ]);
  });

  it('将 reasoning 四字段一并传入全员批量深度分析', async () => {
    await runActionLayer({
      sessionId: SESSION,
      perceptionResult: PERCEPTION_RESULT,
      windowStart: WINDOW_START,
      memberIds: MEMBERS,
      summaryText: '当前讨论聚焦 MVP 范围与优先级。',
      transcripts: TRANSCRIPTS,
    });

    expect(mockAnalyzeMembers).toHaveBeenCalledTimes(1);
    expect(mockAnalyzeMembers).toHaveBeenCalledWith({
      summary: '当前讨论聚焦 MVP 范围与优先级。',
      transcripts: [
        {
          transcript_id: 't1',
          user_id: 'uA',
          speaker_name: '成员A',
          text: '我觉得这个方案可以。',
        },
        {
          transcript_id: 't2',
          user_id: 'uB',
          speaker_name: '成员B',
          text: '我们先限定 MVP 范围，因为这样成本更低。',
        },
      ],
      members: expect.arrayContaining([
        expect.objectContaining({
          user_id: 'uA',
          speaking_ratio: 0.1,
          silence_s: 42,
          ttr: 0.31,
          arg_density: 0.01,
          srep: 0.81,
          info_gain: 0.2,
          reasoning_status: false,
          evidence_status: false,
          reasoning_source: '发言中只有观点表态，没有展开原因。',
          evidence_source: '发言中没有提供例子、数据或事实依据。',
        }),
      ]),
    });
  });

  it('有效结果会写入 push_queue、discussion_states 和 ai_push_analysis', async () => {
    await runActionLayer({
      sessionId: SESSION,
      perceptionResult: PERCEPTION_RESULT,
      windowStart: WINDOW_START,
      memberIds: MEMBERS,
      summaryText: '当前讨论聚焦 MVP 范围与优先级。',
      transcripts: TRANSCRIPTS,
    });

    expect(mockWritePushQueueItem).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'stagnation',
        push_content: '你可以先说说你最担心的是哪一点。',
        analysis_window_start: WINDOW_START,
      }),
    );
    expect(mockWriteDiscussionState).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        state_type: 'stagnation',
        target_user_id: 'uA',
        window_start: WINDOW_START,
        trigger_metrics: expect.objectContaining({
          challenge_type: 'stagnation',
          analysis: 'uA 参与不足，且本轮缺少理由和依据。',
          queued_push_id: 'pq_1',
        }),
      }),
    );
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'stagnation',
        ai_needs_prompt: true,
        ai_content: '你可以先说说你最担心的是哪一点。',
        drop_reason: 'passed',
      }),
    );
  });

  it('anchor 无效时不入队，并写 anchor_invalid 记录', async () => {
    mockAnalyzeMembers.mockResolvedValueOnce([
      {
        user_id: 'uA',
        challenge_type: 'shallow',
        needs_prompt: true,
        analysis: 'uA 阐述浅薄。',
        content: '你可以再补一个具体例子。',
        anchor: {
          transcript_id: 't404',
          speaker_id: 'uA',
          speaker_name: '成员A',
          text: '不存在的锚点',
        },
      },
    ]);

    await runActionLayer({
      sessionId: SESSION,
      perceptionResult: PERCEPTION_RESULT,
      windowStart: WINDOW_START,
      memberIds: MEMBERS,
      summaryText: '当前讨论聚焦 MVP 范围与优先级。',
      transcripts: TRANSCRIPTS,
    });

    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'shallow',
        drop_reason: 'anchor_invalid',
      }),
    );
  });

  it('needs_prompt=false 时只写 needs_prompt_false 记录', async () => {
    mockAnalyzeMembers.mockResolvedValueOnce([
      {
        user_id: 'uA',
        challenge_type: 'none',
        needs_prompt: false,
        analysis: 'uA 当前无需干预。',
        content: '',
        anchor: null,
      },
    ]);

    await runActionLayer({
      sessionId: SESSION,
      perceptionResult: PERCEPTION_RESULT,
      windowStart: WINDOW_START,
      memberIds: MEMBERS,
      summaryText: '当前讨论聚焦 MVP 范围与优先级。',
      transcripts: TRANSCRIPTS,
    });

    expect(mockWritePushQueueItem).not.toHaveBeenCalled();
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockWriteAiPushAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: SESSION,
        target_user_id: 'uA',
        state_type: 'none',
        drop_reason: 'needs_prompt_false',
      }),
    );
  });
});
