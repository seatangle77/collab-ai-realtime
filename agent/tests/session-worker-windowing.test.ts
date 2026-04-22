jest.mock('../src/config', () => ({
  config: {
    agent: {
      shortIntervalMs: 60_000,
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

jest.mock('../src/http/nlp-client', () => ({
  generateGroupSilence: jest.fn(),
  notifyGroupSilence: jest.fn(),
}));

import { SessionWorker } from '../src/session-worker';
import * as queries from '../src/db/queries';
import { runPerceptionPipeline } from '../src/skills/run-perception-pipeline';
import { runActionLayer } from '../src/skills/run-action-layer';

const mockGetSessionMembers = queries.getSessionMembers as jest.MockedFunction<typeof queries.getSessionMembers>;
const mockGetLastSummary = queries.getLastSummary as jest.MockedFunction<typeof queries.getLastSummary>;
const mockGetTranscriptsInWindowPreferCache =
  queries.getTranscriptsInWindowPreferCache as jest.MockedFunction<typeof queries.getTranscriptsInWindowPreferCache>;
const mockRunPerceptionPipeline = runPerceptionPipeline as jest.MockedFunction<typeof runPerceptionPipeline>;
const mockRunActionLayer = runActionLayer as jest.MockedFunction<typeof runActionLayer>;

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
    jest.resetAllMocks();
    mockGetSessionMembers.mockResolvedValue([{ user_id: 'u1' }] as never);
    mockGetLastSummary.mockResolvedValue({ content: '摘要' } as never);
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
  });

  it('稳定阶段使用 60 秒成员级窗口和 120 秒组级窗口', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const scheduledFor = new Date('2026-04-22T10:03:00Z');
    const worker = new SessionWorker('s1', startedAt);

    await (worker as any).runAnalysisPipeline(scheduledFor);

    expect(mockRunPerceptionPipeline).toHaveBeenCalledWith({
      sessionId: 's1',
      memberIds: ['u1'],
      windowStart: new Date('2026-04-22T10:02:00Z'),
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

  it('冷启动阶段组级窗口从会话开始时间起算', async () => {
    const startedAt = new Date('2026-04-22T10:00:00Z');
    const scheduledFor = new Date('2026-04-22T10:01:30Z');
    const worker = new SessionWorker('s1', startedAt);

    await (worker as any).runAnalysisPipeline(scheduledFor);

    expect(mockRunPerceptionPipeline).toHaveBeenCalledWith({
      sessionId: 's1',
      memberIds: ['u1'],
      windowStart: new Date('2026-04-22T10:00:30Z'),
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
});
