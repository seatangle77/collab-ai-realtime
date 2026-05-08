import { createLogger } from '../logger';
import { writeWindowMetrics, writeWindowMetricsBatchReasoning } from '../db/queries';
import { computeSpeakingRatio } from './perception/speaking-ratio';
import { computeSilence } from './perception/silence';
import { computeTtrAndArgDensity } from './perception/ttr-and-arg-density';
import { computeSrep } from './perception/srep';
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
 * 2. info-gain 独立执行，自行提取宽松 TF-IDF 词
 * 3. 汇总所有结果，按用户逐条写入 window_metrics
 *
 * 信息缺口不在本链路内执行。它有自己的业务节奏：
 * 每 60s 召回候选关键词，每 120s 决定是否推送解释按钮。
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

  // ── Step 1~3：启动所有互不依赖的分析任务，避免 reasoning 与 info_gain 串行等待 ───
  logger.info('[Step 1~3] 并行启动：基础指标 / 论证结构 / 信息增益', { sessionId });
  const baseMetricsPromise = Promise.allSettled([
    computeSpeakingRatio(sessionId, windowStart, windowEnd, memberIds),
    computeSilence(sessionId, windowStart, windowEnd, memberIds),
    computeTtrAndArgDensity(sessionId, windowStart, windowEnd, memberIds),
    computeSrep(sessionId, windowStart, windowEnd, memberIds),
  ]);
  const reasoningSettledPromise = toSettled(computeHasReasoning(sessionId, windowStart, windowEnd, memberIds));
  const infoGainSettledPromise = toSettled(computeInfoGain(sessionId, windowStart, windowEnd, memberIds));

  logger.info('[Step 5] 统一等待分析结果：基础指标 / 论证结构 / 信息增益', { sessionId });
  const [baseMetricsSettled, reasoningSettled, igSettled] = await Promise.all([
    toSettled(baseMetricsPromise),
    reasoningSettledPromise,
    infoGainSettledPromise,
  ]);

  if (baseMetricsSettled.status === 'rejected') {
    logger.error('基础指标并行计算失败', { sessionId, message: (baseMetricsSettled.reason as Error)?.message });
  }

  const [
    speakingRatioRes,
    silenceRes,
    ttrAndArgRes,
    srepRes,
  ] = baseMetricsSettled.status === 'fulfilled'
    ? baseMetricsSettled.value
    : [
        { status: 'rejected', reason: baseMetricsSettled.reason } as PromiseRejectedResult,
        { status: 'rejected', reason: baseMetricsSettled.reason } as PromiseRejectedResult,
        { status: 'rejected', reason: baseMetricsSettled.reason } as PromiseRejectedResult,
        { status: 'rejected', reason: baseMetricsSettled.reason } as PromiseRejectedResult,
      ];

  const speakingRatios = settledValue(speakingRatioRes, '发言比例')?.ratios ?? {};
  const silenceSeconds = settledValue(silenceRes, '静默检测')?.silenceSeconds ?? {};
  const ttrAndArg = settledValue(ttrAndArgRes, 'TTR+论证密度');
  const ttrs = ttrAndArg?.ttrs ?? {};
  const argDensities = ttrAndArg?.argDensities ?? {};
  const sreps = settledValue(srepRes, '语义重复度Srep')?.sreps ?? {};

  // ── Step 2：读取已启动的论证结构判定结果（fast_model）────────────────────────
  logger.info('[Step 6] 处理论证结构结果（fast_model，失败则兜底为空）', { sessionId });
  const hasReasoningMap: Record<string, boolean | null> = {};
  const hasEvidenceMap: Record<string, boolean | null> = {};
  const reasoningSourceMap: Record<string, string | null> = {};
  const evidenceSourceMap: Record<string, string | null> = {};

  for (const uid of memberIds) {
    hasReasoningMap[uid] = null;
    hasEvidenceMap[uid] = null;
    reasoningSourceMap[uid] = null;
    evidenceSourceMap[uid] = null;
  }

  if (reasoningSettled.status === 'fulfilled') {
    Object.assign(hasReasoningMap, reasoningSettled.value.hasReasoningMap);
    Object.assign(hasEvidenceMap, reasoningSettled.value.hasEvidenceMap);
    Object.assign(reasoningSourceMap, reasoningSettled.value.reasoningSourceMap);
    Object.assign(evidenceSourceMap, reasoningSettled.value.evidenceSourceMap);
  } else {
    logger.error('论证结构批量判定失败', { sessionId, message: (reasoningSettled.reason as Error)?.message });
  }

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

  // ── Step 3：读取已启动的信息增益计算结果。信息缺口已拆到独立调度链。────────
  logger.info('[Step 6] 处理信息增益结果（InfoGain，失败则兜底为空）', { sessionId });
  let infoGains: Record<string, number | null> = {};

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
  logger.info('===== Pipeline 完成 =====', { sessionId });
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
    skwScores: {},
    keywords: [],
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

async function toSettled<T>(promise: Promise<T>): Promise<PromiseSettledResult<T>> {
  try {
    return { status: 'fulfilled', value: await promise };
  } catch (reason) {
    return { status: 'rejected', reason };
  }
}
