jest.mock('../src/config', () => ({
  config: {
    agent: {
      silenceIntervalMs: 30_000,
      analysisIntervalMs: 60_000,
      infoGapIntervalMs: 60_000,
      infoGapDecisionIntervalMs: 120_000,
      longIntervalMs: 120_000,
      sessionPollMs: 15_000,
    },
  },
}));

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

jest.mock('../src/db/queries', () => ({
  getSessionMembers: jest.fn(),
  getLastSpeakEndGlobal: jest.fn(),
  getLastSummary: jest.fn(),
  getTranscriptsInWindowPreferCache: jest.fn(),
  writeDiscussionState: jest.fn(),
}));

jest.mock('../src/skills/run-perception-pipeline', () => ({
  runPerceptionPipeline: jest.fn(),
}));

jest.mock('../src/skills/run-action-layer', () => ({
  runActionLayer: jest.fn(),
}));

jest.mock('../src/skills/run-summary', () => ({
  runSummary: jest.fn(),
}));

jest.mock('../src/skills/run-push-dispatcher', () => ({
  runPushDispatcher: jest.fn(),
}));

jest.mock('../src/skills/info-gap', () => ({
  recallInfoGapKeywords: jest.fn(),
  decideInfoGapButtons: jest.fn(),
}));

jest.mock('../src/http/nlp-client', () => ({
  generateGroupSilence: jest.fn(),
  notifyGroupSilence: jest.fn(),
}));

import { SessionWorker } from '../src/session-worker';
import * as queries from '../src/db/queries';
import { runPerceptionPipeline } from '../src/skills/run-perception-pipeline';
import { runActionLayer } from '../src/skills/run-action-layer';
import { runSummary } from '../src/skills/run-summary';
import { runPushDispatcher } from '../src/skills/run-push-dispatcher';
import { decideInfoGapButtons, recallInfoGapKeywords } from '../src/skills/info-gap';
import * as nlpClient from '../src/http/nlp-client';

const mockGetSessionMembers = queries.getSessionMembers as jest.MockedFunction<typeof queries.getSessionMembers>;
const mockGetLastSummary = queries.getLastSummary as jest.MockedFunction<typeof queries.getLastSummary>;
const mockGetTranscriptsInWindowPreferCache =
  queries.getTranscriptsInWindowPreferCache as jest.MockedFunction<typeof queries.getTranscriptsInWindowPreferCache>;
const mockRunPerceptionPipeline = runPerceptionPipeline as jest.MockedFunction<typeof runPerceptionPipeline>;
const mockRunActionLayer = runActionLayer as jest.MockedFunction<typeof runActionLayer>;
const mockRunSummary = runSummary as jest.MockedFunction<typeof runSummary>;
const mockRunPushDispatcher = runPushDispatcher as jest.MockedFunction<typeof runPushDispatcher>;
const mockRecallInfoGapKeywords = recallInfoGapKeywords as jest.MockedFunction<typeof recallInfoGapKeywords>;
const mockDecideInfoGapButtons = decideInfoGapButtons as jest.MockedFunction<typeof decideInfoGapButtons>;
const mockGetLastSpeakEndGlobal = queries.getLastSpeakEndGlobal as jest.MockedFunction<typeof queries.getLastSpeakEndGlobal>;
const mockGenerateGroupSilence = nlpClient.generateGroupSilence as jest.MockedFunction<typeof nlpClient.generateGroupSilence>;
const mockNotifyGroupSilence = nlpClient.notifyGroupSilence as jest.MockedFunction<typeof nlpClient.notifyGroupSilence>;

const PERCEPTION_RESULT = {
  speakingRatios: { u1: 0.1 },
  silenceSeconds: { u1: 40 },
  ttrs: { u1: 0.3 },
  argDensities: { u1: 0.01 },
  sreps: { u1: 0.8 },
  infoGains: { u1: 0.2 },
  hasReasoningMap: { u1: false },
  hasEvidenceMap: { u1: false },
  reasoningSourceMap: { u1: '发言中只有观点表态，没有展开原因。' },
  evidenceSourceMap: { u1: '发言中没有提供例子、数据或事实依据。' },
  skwScores: {},
  keywords: [],
};

describe('SessionWorker windowing', () => {
  beforeEach(() => {
    jest.useRealTimers();
    jest.resetAllMocks();
    mockGetSessionMembers.mockResolvedValue([{ user_id: 'u1' }] as never);
    mockGetLastSummary.mockResolvedValue({ content: '摘要' } as never);
    mockGetLastSpeakEndGlobal.mockResolvedValue(null as never);
    mockGetTranscriptsInWindowPreferCache.mockResolvedValue([
      {
        transcript_id: 't1',
        user_id: 'u1',
        speaker_name: '成员甲',
        text: '发言内容',
      },
    ] as never);
    mockRunPerceptionPipeline.mockResolvedValue(PERCEPTION_RESULT as never);
    mockRunActionLayer.mockResolvedValue(undefined);
    mockRunSummary.mockResolvedValue('摘要输出');
    mockRunPushDispatcher.mockResolvedValue(undefined);
    mockRecallInfoGapKeywords.mockResolvedValue({ candidates: [], activeMemberTexts: {} });
    mockDecideInfoGapButtons.mockResolvedValue({ keywords: [], scores: {} });
    mockGenerateGroupSilence.mockResolvedValue('破冰话题');
    mockNotifyGroupSilence.mockResolvedValue(true);
  });

  it('稳定阶段使用 120 秒统一判断窗口，调度仍为 60 秒', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const scheduledFor = new Date('2026-04-22T10:03:00Z');
    const worker = new SessionWorker('s1', startedAt);

    await (worker as any).runAnalysisPipeline(scheduledFor);

    expect(mockRunPerceptionPipeline).toHaveBeenCalledWith({
      sessionId: 's1',
      memberIds: ['u1'],
      windowStart: new Date('2026-04-22T10:01:00Z'),
      windowEnd: scheduledFor,
    });
    expect(mockGetTranscriptsInWindowPreferCache).toHaveBeenCalledWith(
      's1',
      new Date('2026-04-22T10:01:00Z'),
      scheduledFor,
    );
    expect(mockRunActionLayer).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 's1',
        windowStart: new Date('2026-04-22T10:01:00Z'),
        summaryText: '摘要',
      }),
    );
  });

  it('冷启动阶段统一判断窗口从会话开始时间起算', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const scheduledFor = new Date('2026-04-22T10:01:30Z');
    const worker = new SessionWorker('s1', startedAt);

    await (worker as any).runAnalysisPipeline(scheduledFor);

    expect(mockRunPerceptionPipeline).toHaveBeenCalledWith({
      sessionId: 's1',
      memberIds: ['u1'],
      windowStart: startedAt,
      windowEnd: scheduledFor,
    });
    expect(mockGetTranscriptsInWindowPreferCache).toHaveBeenCalledWith(
      's1',
      startedAt,
      scheduledFor,
    );
    expect(mockRunActionLayer).toHaveBeenCalledWith(
      expect.objectContaining({
        windowStart: startedAt,
      }),
    );
  });

  it('成员分析链在感知层后并行读取摘要和窗口发言', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const scheduledFor = new Date('2026-04-22T10:03:00Z');
    const worker = new SessionWorker('s1', startedAt);
    let resolveSummary: ((value: { content: string }) => void) | undefined;

    mockGetLastSummary.mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveSummary = resolve;
      }) as never,
    );

    const runPromise = (worker as any).runAnalysisPipeline(scheduledFor);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(mockRunPerceptionPipeline).toHaveBeenCalledTimes(1);
    expect(mockGetLastSummary).toHaveBeenCalledTimes(1);
    expect(mockGetTranscriptsInWindowPreferCache).toHaveBeenCalledTimes(1);
    expect(mockGetTranscriptsInWindowPreferCache).toHaveBeenCalledWith(
      's1',
      new Date('2026-04-22T10:01:00Z'),
      scheduledFor,
    );
    expect(mockRunActionLayer).not.toHaveBeenCalled();

    resolveSummary?.({ content: '并行摘要' });
    await runPromise;

    expect(mockRunActionLayer).toHaveBeenCalledWith(
      expect.objectContaining({
        summaryText: '并行摘要',
        transcripts: expect.arrayContaining([
          expect.objectContaining({ transcript_id: 't1', text: '发言内容' }),
        ]),
      }),
    );
  });

  it('成员分析链读取上下文失败时不启动行动层', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const scheduledFor = new Date('2026-04-22T10:03:00Z');
    const worker = new SessionWorker('s1', startedAt);

    mockGetLastSummary.mockRejectedValueOnce(new Error('summary db timeout') as never);

    await (worker as any).runAnalysisPipeline(scheduledFor);

    expect(mockGetLastSummary).toHaveBeenCalledTimes(1);
    expect(mockGetTranscriptsInWindowPreferCache).toHaveBeenCalledTimes(1);
    expect(mockRunActionLayer).not.toHaveBeenCalled();
  });

  it('群体沉默检测、成员分析和摘要使用独立调度节奏', async () => {
    jest.useFakeTimers();
    const startedAt = new Date('2026-04-22T10:00:00Z');
    jest.setSystemTime(startedAt);

    const worker = new SessionWorker('s1', startedAt);
    const checkGroupSilenceSpy = jest
      .spyOn(worker as never, 'checkGroupSilence' as never)
      .mockResolvedValue(undefined as never);
    const runAnalysisPipelineSpy = jest
      .spyOn(worker as never, 'runAnalysisPipeline' as never)
      .mockResolvedValue(undefined as never);
    const runSummaryPipelineSpy = jest
      .spyOn(worker as never, 'runSummaryPipeline' as never)
      .mockResolvedValue(undefined as never);
    const runInfoGapPipelineSpy = jest
      .spyOn(worker as never, 'runInfoGapPipeline' as never)
      .mockResolvedValue(undefined as never);

    worker.start();

    await jest.advanceTimersByTimeAsync(30_000);
    expect(checkGroupSilenceSpy).toHaveBeenCalledTimes(1);
    expect(runAnalysisPipelineSpy).toHaveBeenCalledTimes(0);
    expect(runInfoGapPipelineSpy).toHaveBeenCalledTimes(0);
    expect(runSummaryPipelineSpy).toHaveBeenCalledTimes(0);
    expect(checkGroupSilenceSpy).toHaveBeenLastCalledWith(new Date('2026-04-22T10:00:30Z'));

    await jest.advanceTimersByTimeAsync(30_000);
    expect(checkGroupSilenceSpy).toHaveBeenCalledTimes(2);
    expect(runAnalysisPipelineSpy).toHaveBeenCalledTimes(1);
    expect(runInfoGapPipelineSpy).toHaveBeenCalledTimes(1);
    expect(runSummaryPipelineSpy).toHaveBeenCalledTimes(0);
    expect(runAnalysisPipelineSpy).toHaveBeenLastCalledWith(new Date('2026-04-22T10:01:00Z'));
    expect(runInfoGapPipelineSpy).toHaveBeenLastCalledWith(new Date('2026-04-22T10:01:00Z'));

    await jest.advanceTimersByTimeAsync(45_000);
    expect(checkGroupSilenceSpy).toHaveBeenCalledTimes(3);
    expect(runAnalysisPipelineSpy).toHaveBeenCalledTimes(1);
    expect(runInfoGapPipelineSpy).toHaveBeenCalledTimes(1);
    expect(runSummaryPipelineSpy).toHaveBeenCalledTimes(1);
    expect(runSummaryPipelineSpy).toHaveBeenLastCalledWith(new Date('2026-04-22T10:01:45Z'));

    worker.stop();
    jest.useRealTimers();
  });

  it('推送调度使用独立 120 秒节奏，不再 5 秒轮询队列', async () => {
    jest.useFakeTimers();
    const startedAt = new Date('2026-04-22T10:00:00Z');
    jest.setSystemTime(startedAt);

    const worker = new SessionWorker('s1', startedAt);
    jest
      .spyOn(worker as never, 'checkGroupSilence' as never)
      .mockResolvedValue(undefined as never);
    jest
      .spyOn(worker as never, 'runAnalysisPipeline' as never)
      .mockResolvedValue(undefined as never);
    jest
      .spyOn(worker as never, 'runSummaryPipeline' as never)
      .mockResolvedValue(undefined as never);
    jest
      .spyOn(worker as never, 'runInfoGapPipeline' as never)
      .mockResolvedValue(undefined as never);

    worker.start();

    await jest.advanceTimersByTimeAsync(5_000);
    expect(mockRunPushDispatcher).not.toHaveBeenCalled();

    await jest.advanceTimersByTimeAsync(114_999);
    expect(mockRunPushDispatcher).not.toHaveBeenCalled();

    await jest.advanceTimersByTimeAsync(1);
    expect(mockRunPushDispatcher).toHaveBeenCalledTimes(1);
    expect(mockRunPushDispatcher).toHaveBeenLastCalledWith('s1');

    await jest.advanceTimersByTimeAsync(119_999);
    expect(mockRunPushDispatcher).toHaveBeenCalledTimes(1);

    await jest.advanceTimersByTimeAsync(1);
    expect(mockRunPushDispatcher).toHaveBeenCalledTimes(2);

    worker.stop();
    jest.useRealTimers();
  });

  it('信息缺口每 60 秒召回关键词，每 120 秒基于最近两轮候选词决策', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const worker = new SessionWorker('s1', startedAt);
    const firstScheduledFor = new Date('2026-04-22T10:01:00Z');
    const secondScheduledFor = new Date('2026-04-22T10:02:00Z');
    const firstCandidate = {
      word: 'MVP',
      needs_prompt: true,
      target_user_id: 'u2',
      reason: '可能不理解 MVP',
      sourceByUser: { u1: '我们先做 MVP' },
      activeMemberIds: ['u1', 'u2'],
      windowStart: startedAt,
      windowEnd: firstScheduledFor,
    };
    const secondCandidate = {
      word: '冷启动',
      needs_prompt: true,
      target_user_id: 'u1',
      reason: '可能不理解冷启动',
      sourceByUser: { u2: '冷启动是重点' },
      activeMemberIds: ['u1', 'u2'],
      windowStart: firstScheduledFor,
      windowEnd: secondScheduledFor,
    };

    mockGetSessionMembers.mockResolvedValue([{ user_id: 'u1' }, { user_id: 'u2' }] as never);
    mockRecallInfoGapKeywords
      .mockResolvedValueOnce({ candidates: [firstCandidate], activeMemberTexts: {} })
      .mockResolvedValueOnce({ candidates: [secondCandidate], activeMemberTexts: {} });

    await (worker as any).runInfoGapPipeline(firstScheduledFor);
    expect(mockRecallInfoGapKeywords).toHaveBeenLastCalledWith(
      's1',
      startedAt,
      firstScheduledFor,
      ['u1', 'u2'],
    );
    expect(mockDecideInfoGapButtons).not.toHaveBeenCalled();

    await (worker as any).runInfoGapPipeline(secondScheduledFor);
    expect(mockRecallInfoGapKeywords).toHaveBeenLastCalledWith(
      's1',
      firstScheduledFor,
      secondScheduledFor,
      ['u1', 'u2'],
    );
    expect(mockDecideInfoGapButtons).toHaveBeenCalledWith({
      sessionId: 's1',
      windowStart: startedAt,
      memberIds: ['u1', 'u2'],
      candidates: [firstCandidate, secondCandidate],
    });
  });
});
