import { createLogger } from '../logger';
import { writeWindowMetrics, writeWindowMetricsBatchReasoning } from '../db/queries';
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
  reasoningSourceMap: Record<string, string | null>;
  evidenceSourceMap: Record<string, string | null>;
  skwScores: Record<string, Record<string, Record<string, number>>>;
  keywords: string[];
}

/**
 * 完整感知层 Pipeline。
 *
 * 当前由上层成员分析链按文档节奏触发：
 * 1. 每 60s 触发一次
 * 2. 本层处理最近 60s 的成员级窗口数据
 * 3. 输出结果供后续 120s 组级深度分析使用
 *
 * 执行顺序：
 * 1. speaking-ratio / silence / ttr / arg-density / srep 并行执行（互不依赖）
 * 2. skw 与 info-gain 并行执行（互不依赖：skw 用 LLM 召回专业词，info-gain 自行提取宽松 TF-IDF 词）
 * 3. 汇总所有结果，按用户逐条写入 window_metrics
 */
export async function runPerceptionPipeline(input: PipelineInput): Promise<PipelineResult | undefined> {
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

  // ── Step 1：并行执行互不依赖的 5 个纯计算 skill ──────────────────────────────
  logger.info('[Step 1] 并行执行：发言比例 / 静默检测 / TTR / 论证密度 / 语义重复', { sessionId });
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

  const speakingRatios = settledValue(speakingRatioRes, '发言比例')?.ratios ?? {};
  const silenceSeconds = settledValue(silenceRes, '静默检测')?.silenceSeconds ?? {};
  const ttrs = settledValue(ttrRes, '词汇多样性TTR')?.ttrs ?? {};
  const argDensities = settledValue(argDensityRes, '论证密度')?.argDensities ?? {};
  const sreps = settledValue(srepRes, '语义重复度Srep')?.sreps ?? {};

  // ── Step 2：论证结构批量判定（fast_model，同窗口，await 阻塞，硬前置）───────
  logger.info('[Step 2] 论证结构批量判定（fast_model）', { sessionId });
  const reasoningResult = await computeHasReasoning(sessionId, windowStart, windowEnd, memberIds);
  const hasReasoningMap = reasoningResult.hasReasoningMap;
  const hasEvidenceMap = reasoningResult.hasEvidenceMap;
  const reasoningSourceMap = reasoningResult.reasoningSourceMap;
  const evidenceSourceMap = reasoningResult.evidenceSourceMap;

  // 写入 window_metrics_batch_reasoning（batch_has_reasoning 完整原始输出）
  void writeWindowMetricsBatchReasoning({
    session_id: sessionId,
    window_start: windowStart,
    members: memberIds
      .filter((uid) => hasReasoningMap[uid] !== null)
      .map((uid) => ({
        user_id: uid,
        reasoning_status: hasReasoningMap[uid] ?? null,
        evidence_status: hasEvidenceMap[uid] ?? null,
        reasoning_source: reasoningSourceMap[uid] ?? null,
        evidence_source: evidenceSourceMap[uid] ?? null,
      })),
  }).catch((err) => {
    logger.error('写入 window_metrics_batch_reasoning 失败', { sessionId, message: (err as Error).message });
  });

  // ── Step 2 & 3：skw 与 info-gain 并行执行（互不依赖）──────────────────────
  logger.info('[Step 2+3] 并行执行：关键词提取与跨成员语义分析（Skw）+ 信息增益计算（InfoGain）', { sessionId });
  let currentKeywords: string[] = [];
  let skwRes: Awaited<ReturnType<typeof computeSkw>> | null = null;
  let infoGains: Record<string, number | null> = {};

  const [skwSettled, igSettled] = await Promise.allSettled([
    computeSkw(sessionId, windowStart, windowEnd, memberIds),
    computeInfoGain(sessionId, windowStart, windowEnd, memberIds),
  ]);

  if (skwSettled.status === 'fulfilled') {
    skwRes = skwSettled.value;
    currentKeywords = skwRes.keywords;
  } else {
    logger.error('Skw 关键词分析失败', { sessionId, message: (skwSettled.reason as Error)?.message });
  }

  if (igSettled.status === 'fulfilled') {
    infoGains = igSettled.value.infoGains;
  } else {
    logger.error('InfoGain 信息增益计算失败', { sessionId, message: (igSettled.reason as Error)?.message });
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
        reasoning_source: reasoningSourceMap[uid] ?? null,
        evidence_source: evidenceSourceMap[uid] ?? null,
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
    reasoningSourceMap,
    evidenceSourceMap,
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
