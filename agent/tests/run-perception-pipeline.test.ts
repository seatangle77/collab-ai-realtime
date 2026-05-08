import { runPerceptionPipeline } from '../src/skills/run-perception-pipeline';
import * as speakingRatio from '../src/skills/perception/speaking-ratio';
import * as silence from '../src/skills/perception/silence';
import * as ttrAndArgDensity from '../src/skills/perception/ttr-and-arg-density';
import * as srep from '../src/skills/perception/srep';
import * as infoGain from '../src/skills/perception/info-gain';
import * as reasoning from '../src/skills/perception/reasoning';
import * as queries from '../src/db/queries';

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

jest.mock('../src/skills/perception/speaking-ratio');
jest.mock('../src/skills/perception/silence');
jest.mock('../src/skills/perception/ttr-and-arg-density');
jest.mock('../src/skills/perception/srep');
jest.mock('../src/skills/perception/info-gain');
jest.mock('../src/skills/perception/reasoning');
jest.mock('../src/db/queries');

const mockComputeSpeakingRatio = speakingRatio.computeSpeakingRatio as jest.MockedFunction<
  typeof speakingRatio.computeSpeakingRatio
>;
const mockComputeSilence = silence.computeSilence as jest.MockedFunction<typeof silence.computeSilence>;
const mockComputeTtrAndArgDensity = ttrAndArgDensity.computeTtrAndArgDensity as jest.MockedFunction<
  typeof ttrAndArgDensity.computeTtrAndArgDensity
>;
const mockComputeSrep = srep.computeSrep as jest.MockedFunction<typeof srep.computeSrep>;
const mockComputeInfoGain = infoGain.computeInfoGain as jest.MockedFunction<typeof infoGain.computeInfoGain>;
const mockComputeHasReasoning = reasoning.computeHasReasoning as jest.MockedFunction<
  typeof reasoning.computeHasReasoning
>;
const mockWriteWindowMetrics = queries.writeWindowMetrics as jest.MockedFunction<typeof queries.writeWindowMetrics>;
const mockWriteWindowMetricsBatchReasoning = queries.writeWindowMetricsBatchReasoning as jest.MockedFunction<
  typeof queries.writeWindowMetricsBatchReasoning
>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe('runPerceptionPipeline', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockWriteWindowMetrics.mockResolvedValue(undefined);
    mockWriteWindowMetricsBatchReasoning.mockResolvedValue(undefined);
  });

  it('同时启动基础指标、论证结构和信息增益，避免 reasoning 与 info_gain 串行等待', async () => {
    const baseSpeaking = deferred<{ ratios: Record<string, number> }>();
    const baseSilence = deferred<{ silenceSeconds: Record<string, number> }>();
    const baseTtr = deferred<{
      ttrs: Record<string, number | null>;
      argDensities: Record<string, number | null>;
    }>();
    const baseSrep = deferred<{ sreps: Record<string, number | null> }>();
    const reasoningResult = deferred<Awaited<ReturnType<typeof reasoning.computeHasReasoning>>>();
    const infoGainResult = deferred<Awaited<ReturnType<typeof infoGain.computeInfoGain>>>();

    mockComputeSpeakingRatio.mockReturnValue(baseSpeaking.promise);
    mockComputeSilence.mockReturnValue(baseSilence.promise);
    mockComputeTtrAndArgDensity.mockReturnValue(baseTtr.promise);
    mockComputeSrep.mockReturnValue(baseSrep.promise);
    mockComputeHasReasoning.mockReturnValue(reasoningResult.promise);
    mockComputeInfoGain.mockReturnValue(infoGainResult.promise);

    const pipelinePromise = runPerceptionPipeline({
      sessionId: 's1',
      memberIds: ['u1'],
      windowStart: new Date('2026-04-22T10:00:00Z'),
      windowEnd: new Date('2026-04-22T10:02:00Z'),
    });

    await Promise.resolve();

    expect(mockComputeSpeakingRatio).toHaveBeenCalledTimes(1);
    expect(mockComputeSilence).toHaveBeenCalledTimes(1);
    expect(mockComputeTtrAndArgDensity).toHaveBeenCalledTimes(1);
    expect(mockComputeSrep).toHaveBeenCalledTimes(1);
    expect(mockComputeHasReasoning).toHaveBeenCalledTimes(1);
    expect(mockComputeInfoGain).toHaveBeenCalledTimes(1);

    baseSpeaking.resolve({ ratios: { u1: 0.2 } });
    baseSilence.resolve({ silenceSeconds: { u1: 12 } });
    baseTtr.resolve({ ttrs: { u1: 0.5 }, argDensities: { u1: 0.1 } });
    baseSrep.resolve({ sreps: { u1: 0.3 } });
    reasoningResult.resolve({
      hasReasoningMap: { u1: true },
      hasEvidenceMap: { u1: false },
      reasoningSourceMap: { u1: '有理由展开' },
      evidenceSourceMap: { u1: '没有证据' },
    });
    infoGainResult.resolve({ infoGains: { u1: 0.7 } });

    const result = await pipelinePromise;

    expect(result?.hasReasoningMap.u1).toBe(true);
    expect(result?.infoGains.u1).toBe(0.7);
    expect(mockWriteWindowMetrics).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: 's1',
        user_id: 'u1',
        has_reasoning: true,
        info_gain: 0.7,
      }),
    );
  });
});
