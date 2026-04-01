import { createLogger } from '../logger';
import { writeWindowMetrics } from '../db/queries';
import { computeSpeakingRatio } from './perception/speaking-ratio';
import { computeSilence } from './perception/silence';
import { computeTtr } from './perception/ttr';
import { computeArgDensity } from './perception/arg-density';
import { computeSrep } from './perception/srep';
import { computeSkw } from './perception/skw';
import { computeInfoGain } from './perception/info-gain';

const logger = createLogger('pipeline');

export interface PipelineInput {
  sessionId: string;
  memberIds: string[];
  windowStart: Date;
  windowEnd: Date;
}

/**
 * 完整感知层 Pipeline（每 120s 触发一次）
 *
 * 执行顺序：
 * 1. speaking-ratio / silence / ttr / arg-density / srep 并行执行（互不依赖）
 * 2. skw 依赖 tfidf，单独执行（内部已处理 DB 写入）
 * 3. info-gain 依赖 skw 产出的 keywords，最后执行
 * 4. 汇总所有结果，按用户逐条写入 window_metrics
 */
export async function runPerceptionPipeline(input: PipelineInput): Promise<void> {
  const { sessionId, memberIds, windowStart, windowEnd } = input;

  if (memberIds.length === 0) {
    logger.warn('No members found, skipping pipeline', { sessionId });
    return;
  }

  logger.info('Pipeline start', {
    sessionId,
    members: memberIds.length,
    windowStart: windowStart.toISOString(),
    windowEnd: windowEnd.toISOString(),
  });

  // ── Step 1：并行执行互不依赖的 5 个 skill ────────────────────────────────────
  const [
    speakingRatioRes,
    silenceRes,
    ttrRes,
    argDensityRes,
    srepRes,
  ] = await Promise.allSettled([
    computeSpeakingRatio(sessionId, windowStart, windowEnd, memberIds),
    computeSilence(sessionId, windowStart, windowEnd, memberIds),
    computeTtr(sessionId, windowStart, windowEnd, memberIds),
    computeArgDensity(sessionId, windowStart, windowEnd, memberIds),
    computeSrep(sessionId, windowStart, windowEnd, memberIds),
  ]);

  const speakingRatios = settledValue(speakingRatioRes, 'speaking-ratio')?.ratios ?? {};
  const silenceSeconds = settledValue(silenceRes, 'silence')?.silenceSeconds ?? {};
  const ttrs = settledValue(ttrRes, 'ttr')?.ttrs ?? {};
  const argDensities = settledValue(argDensityRes, 'arg-density')?.argDensities ?? {};
  const sreps = settledValue(srepRes, 'srep')?.sreps ?? {};

  // ── Step 2：skw（内部写 keyword_skw 表）────────────────────────────────────
  let currentKeywords: string[] = [];
  try {
    const skwRes = await computeSkw(sessionId, windowStart, windowEnd, memberIds);
    currentKeywords = skwRes.keywords;
  } catch (err) {
    logger.error('skw failed', { sessionId, message: (err as Error).message });
  }

  // ── Step 3：info-gain（依赖 currentKeywords）─────────────────────────────
  let infoGains: Record<string, number | null> = {};
  try {
    const igRes = await computeInfoGain(
      sessionId,
      windowStart,
      windowEnd,
      memberIds,
      currentKeywords,
    );
    infoGains = igRes.infoGains;
  } catch (err) {
    logger.error('info-gain failed', { sessionId, message: (err as Error).message });
  }

  // ── Step 4：逐用户写入 window_metrics ─────────────────────────────────────
  await Promise.allSettled(
    memberIds.map((uid) =>
      writeWindowMetrics({
        session_id: sessionId,
        user_id: uid,
        window_start: windowStart,
        window_end: windowEnd,
        speaking_ratio: speakingRatios[uid] ?? 0,
        silence_s: silenceSeconds[uid] ?? (windowEnd.getTime() - windowStart.getTime()) / 1000,
        ttr: ttrs[uid] ?? null,
        arg_density: argDensities[uid] ?? null,
        srep: sreps[uid] ?? null,
        info_gain: infoGains[uid] ?? null,
        has_reasoning: null,   // Week 3 推理层填充
        has_evidence: null,    // Week 3 推理层填充
      }).catch((err) => {
        logger.error('writeWindowMetrics failed', { sessionId, uid, message: (err as Error).message });
      }),
    ),
  );

  logger.info('Pipeline done', { sessionId, members: memberIds.length });
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function settledValue<T>(
  result: PromiseSettledResult<T>,
  label: string,
): T | null {
  if (result.status === 'fulfilled') return result.value;
  logger.error(`${label} skill failed`, { message: (result.reason as Error)?.message });
  return null;
}
