import { createLogger } from '../logger';
import { writeWindowMetrics } from '../db/queries';
import { computeSpeakingRatio } from './perception/speaking-ratio';
import { computeSilence } from './perception/silence';
import { computeTtr } from './perception/ttr';
import { computeArgDensity } from './perception/arg-density';
import { computeSrep } from './perception/srep';
import { computeSkw } from './perception/skw';
import { computeInfoGain } from './perception/info-gain';
import { computeHasReasoning } from './perception/reasoning';

const logger = createLogger('pipeline');

export interface PipelineInput {
  sessionId: string;
  memberIds: string[];
  windowStart: Date;
  windowEnd: Date;
}

export interface PipelineResult {
  speakingRatios: Record<string, number>;
  silenceSeconds: Record<string, number>;
  ttrs: Record<string, number | null>;
  argDensities: Record<string, number | null>;
  sreps: Record<string, number | null>;
  infoGains: Record<string, number | null>;
  hasReasoningMap: Record<string, boolean | null>;
  hasEvidenceMap: Record<string, boolean | null>;
  skwScores: Record<string, Record<string, Record<string, number>>>;
  keywords: string[];
}

/**
 * 完整感知层 Pipeline（每 120s 触发一次）
 *
 * 执行顺序：
 * 1. speaking-ratio / silence / ttr / arg-density / srep / has_reasoning 并行执行（互不依赖）
 * 2. skw 依赖 tfidf，单独执行（内部已处理 DB 写入）
 * 3. info-gain 依赖 skw 产出的 keywords，最后执行
 * 4. 汇总所有结果，按用户逐条写入 window_metrics
 */
export async function runPerceptionPipeline(input: PipelineInput): Promise<PipelineResult> {
  const { sessionId, memberIds, windowStart, windowEnd } = input;

  if (memberIds.length === 0) {
    logger.warn('成员列表为空，跳过 pipeline', { sessionId });
    return;
  }

  logger.info('===== 感知层 Pipeline 开始 =====', {
    sessionId,
    成员数: memberIds.length,
    窗口开始: windowStart.toISOString(),
    窗口结束: windowEnd.toISOString(),
  });

  // ── Step 1：并行执行互不依赖的 6 个 skill ────────────────────────────────────
  logger.info('[Step 1] 并行执行：发言比例 / 静默检测 / TTR / 论证密度 / 语义重复 / Qwen论证检测', { sessionId });
  const [
    speakingRatioRes,
    silenceRes,
    ttrRes,
    argDensityRes,
    srepRes,
    reasoningRes,
  ] = await Promise.allSettled([
    computeSpeakingRatio(sessionId, windowStart, windowEnd, memberIds),
    computeSilence(sessionId, windowStart, windowEnd, memberIds),
    computeTtr(sessionId, windowStart, windowEnd, memberIds),
    computeArgDensity(sessionId, windowStart, windowEnd, memberIds),
    computeSrep(sessionId, windowStart, windowEnd, memberIds),
    computeHasReasoning(sessionId, windowStart, windowEnd, memberIds),
  ]);

  const speakingRatios = settledValue(speakingRatioRes, '发言比例')?.ratios ?? {};
  const silenceSeconds = settledValue(silenceRes, '静默检测')?.silenceSeconds ?? {};
  const ttrs = settledValue(ttrRes, '词汇多样性TTR')?.ttrs ?? {};
  const argDensities = settledValue(argDensityRes, '论证密度')?.argDensities ?? {};
  const sreps = settledValue(srepRes, '语义重复度Srep')?.sreps ?? {};
  const reasoningResult = settledValue(reasoningRes, 'Qwen论证检测');
  const hasReasoningMap = reasoningResult?.hasReasoningMap ?? {};
  const hasEvidenceMap = reasoningResult?.hasEvidenceMap ?? {};

  // ── Step 2：skw（内部写 keyword_skw 表）────────────────────────────────────
  logger.info('[Step 2] 执行关键词提取与跨成员语义分析（Skw）', { sessionId });
  let currentKeywords: string[] = [];
  let skwRes: Awaited<ReturnType<typeof computeSkw>> | null = null;
  try {
    skwRes = await computeSkw(sessionId, windowStart, windowEnd, memberIds);
    currentKeywords = skwRes.keywords;
  } catch (err) {
    logger.error('Skw 关键词分析失败', { sessionId, message: (err as Error).message });
  }

  // ── Step 3：info-gain（依赖 currentKeywords）─────────────────────────────
  logger.info('[Step 3] 执行信息增益计算（InfoGain）', { sessionId });
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
    logger.error('InfoGain 信息增益计算失败', { sessionId, message: (err as Error).message });
  }

  // ── Step 4：逐用户写入 window_metrics ─────────────────────────────────────
  logger.info('[Step 4] 写入数据库 window_metrics', { sessionId });
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
        has_reasoning: hasReasoningMap[uid] ?? null,
        has_evidence: hasEvidenceMap[uid] ?? null,
      }).catch((err) => {
        logger.error('写入 window_metrics 失败', { sessionId, uid, message: (err as Error).message });
      }),
    ),
  );

  // ── 打印每位成员汇总（单行紧凑格式）────────────────────────────────────────
  logger.info(`===== Pipeline 完成 关键词：${currentKeywords.join('、') || '无'} =====`, { sessionId });
  for (const uid of memberIds) {
    const ratio  = speakingRatios[uid] ?? 0;
    const sil    = silenceSeconds[uid] ?? null;
    const ttr    = ttrs[uid] ?? null;
    const argD   = argDensities[uid] ?? null;
    const srep   = sreps[uid] ?? null;
    const ig     = infoGains[uid] ?? null;
    const rsn    = hasReasoningMap[uid] ?? null;
    const evi    = hasEvidenceMap[uid] ?? null;

    logger.info(
      `用户 ${uid} | 发言${(ratio * 100).toFixed(1)}%${ratio < 0.15 ? '⚠️' : ''} | 静默${sil !== null ? sil.toFixed(1) : '-'}s` +
      ` | TTR=${ttr !== null ? ttr.toFixed(3) : '-'}(${ttr === null ? '-' : ttr >= 0.7 ? '丰富' : ttr >= 0.4 ? '中等' : '⚠️单调'})` +
      ` | 论证密度=${argD !== null ? argD.toFixed(3) : '-'}(${argD === null ? '-' : argD >= 0.1 ? '正常' : '⚠️缺乏'})` +
      ` | Srep=${srep !== null ? srep.toFixed(3) : '-'}(${srep === null ? '-' : srep > 0.65 ? '⚠️重复' : '正常'})` +
      ` | 增益=${ig !== null ? ig.toFixed(3) : '-'}(${ig === null ? '-' : ig >= 0.3 ? '有新内容' : '⚠️停滞'})` +
      ` | 论证=${rsn === null ? '-' : rsn ? '✅' : '❌'} 证据=${evi === null ? '-' : evi ? '✅' : '❌'}`,
      { sessionId },
    );
  }

  logger.info('===== Pipeline 结束 =====', { sessionId });

  return {
    speakingRatios,
    silenceSeconds,
    ttrs,
    argDensities,
    sreps,
    infoGains,
    hasReasoningMap,
    hasEvidenceMap,
    skwScores: skwRes?.scores ?? {},
    keywords: currentKeywords,
  };
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function settledValue<T>(
  result: PromiseSettledResult<T>,
  label: string,
): T | null {
  if (result.status === 'fulfilled') return result.value;
  logger.error(`${label} 技能执行失败`, { message: (result.reason as Error)?.message });
  return null;
}
