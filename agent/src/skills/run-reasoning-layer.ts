import { createLogger } from '../logger';
import type { PipelineResult } from './run-perception-pipeline';

const logger = createLogger('reasoning-layer');

// ── 阈值 ──────────────────────────────────────────────────────────────────────

const THRESHOLDS = {
  GROUP_SILENCE_S:    30,
  SPEAKING_RATIO_LOW: 0.15,
  TTR_LOW:            0.4,
  ARG_DENSITY_LOW:    0.02,
  SREP_HIGH:          0.65,
  INFO_GAIN_LOW:      0.3,
  SKW_GAP:            0.3,
  SKW_CLOSE:          0.6,
} as const;

// ── 类型 ──────────────────────────────────────────────────────────────────────

export type TriggerType =
  | 'group_silence'
  | 'low_participation'
  | 'shallow_discussion'
  | 'info_gap';

export interface Trigger {
  type: TriggerType;
  userId?: string;                         // 非群体触发时的触发成员
  targetUsers: string[];                   // 实际推送对象
  keyword?: string;                        // info_gap 专用
  skwScore?: number;                       // info_gap 专用
  triggerMetrics: Record<string, unknown>; // 存入 discussion_states.trigger_metrics
}

// ── 主函数 ────────────────────────────────────────────────────────────────────

export function runReasoningLayer(
  result: PipelineResult,
  memberIds: string[],
): Trigger[] {
  const triggers: Trigger[] = [];

  triggers.push(...detectGroupSilence(result, memberIds));
  triggers.push(...detectLowParticipation(result, memberIds));
  triggers.push(...detectShallowDiscussion(result, memberIds));
  triggers.push(...detectInfoGap(result, memberIds));

  logger.info(`推理层完成，触发 ${triggers.length} 条`, {
    触发列表: triggers.map((t) => `${t.type}${t.userId ? `(${t.userId})` : ''}${t.keyword ? `[${t.keyword}]` : ''}`).join(', ') || '无',
  });

  return triggers;
}

// ── ① 群体停滞 ────────────────────────────────────────────────────────────────

function detectGroupSilence(result: PipelineResult, memberIds: string[]): Trigger[] {
  const silences = memberIds.map((uid) => result.silenceSeconds[uid] ?? 0);
  const allSilent = silences.every((s) => s > THRESHOLDS.GROUP_SILENCE_S);

  if (!allSilent) return [];

  const maxSilence = Math.max(...silences);
  logger.info(`[群体停滞] 全组静默 ${maxSilence.toFixed(1)}s > ${THRESHOLDS.GROUP_SILENCE_S}s → 触发`);

  return [{
    type: 'group_silence',
    targetUsers: memberIds,
    triggerMetrics: { silence_s: Math.round(maxSilence) },
  }];
}

// ── ② 个人停滞 ────────────────────────────────────────────────────────────────

function detectLowParticipation(result: PipelineResult, memberIds: string[]): Trigger[] {
  const triggers: Trigger[] = [];

  for (const uid of memberIds) {
    const ratio = result.speakingRatios[uid] ?? 0;
    if (ratio < THRESHOLDS.SPEAKING_RATIO_LOW) {
      logger.info(`[个人停滞] 用户 ${uid} 发言比例 ${(ratio * 100).toFixed(1)}% < 15% → 触发`);
      triggers.push({
        type: 'low_participation',
        userId: uid,
        targetUsers: [uid],
        triggerMetrics: { speaking_ratio: ratio },
      });
    }
  }

  return triggers;
}

// ── ③ 阐述浅薄 ───────────────────────────────────────────────────────────────

function detectShallowDiscussion(result: PipelineResult, memberIds: string[]): Trigger[] {
  const triggers: Trigger[] = [];

  for (const uid of memberIds) {
    const srep    = result.sreps[uid] ?? null;
    const ig      = result.infoGains[uid] ?? null;
    const ttr     = result.ttrs[uid] ?? null;
    const argD    = result.argDensities[uid] ?? null;
    const hasRsn  = result.hasReasoningMap[uid] ?? null;
    const hasEvi  = result.hasEvidenceMap[uid] ?? null;

    // 3个条件独立判断
    const condA = srep !== null && ig !== null && srep > THRESHOLDS.SREP_HIGH && ig < THRESHOLDS.INFO_GAIN_LOW;
    const condB = ttr !== null && ttr < THRESHOLDS.TTR_LOW;
    const condC = argD !== null && argD < THRESHOLDS.ARG_DENSITY_LOW
                  && hasRsn === false && hasEvi === false;

    const triggered: string[] = [];
    if (condA) triggered.push('观点重复');
    if (condB) triggered.push('用词单调');
    if (condC) triggered.push('缺乏论证');

    if (triggered.length < 2) continue;

    logger.info(`[阐述浅薄] 用户 ${uid} 触发：${triggered.join('+')} → 触发`);

    const metrics: Record<string, unknown> = {};
    if (condA) { metrics.srep = srep; metrics.info_gain = ig; }
    if (condB) { metrics.ttr = ttr; }
    if (condC) { metrics.arg_density = argD; metrics.has_reasoning = hasRsn; metrics.has_evidence = hasEvi; }

    // triggered_metrics 里记录触发了哪些条件，供 Prompt 使用
    const metricDesc: string[] = [];
    if (condA) metricDesc.push(`Srep=${(srep as number).toFixed(3)}（高于0.65且新观点不足，观点出现重复）`);
    if (condB) metricDesc.push(`TTR=${(ttr as number).toFixed(3)}（低于0.4，用词较单调）`);
    if (condC) metricDesc.push(`论证词密度=${(argD as number).toFixed(3)}（低于0.02且缺乏原因或证据，缺乏逻辑论证）`);

    triggers.push({
      type: 'shallow_discussion',
      userId: uid,
      targetUsers: [uid],
      triggerMetrics: { ...metrics, description: metricDesc.join(' / ') },
    });
  }

  return triggers;
}

// ── ④ 信息缺口 ───────────────────────────────────────────────────────────────

function detectInfoGap(result: PipelineResult, memberIds: string[]): Trigger[] {
  const triggers: Trigger[] = [];
  const { skwScores, keywords } = result;

  for (const keyword of keywords) {
    const kwScores = skwScores[keyword];
    if (!kwScores) continue;

    // 收集所有 pair 的分数
    const pairs: Array<{ a: string; b: string; score: number }> = [];
    for (let i = 0; i < memberIds.length; i++) {
      for (let j = i + 1; j < memberIds.length; j++) {
        const a = memberIds[i];
        const b = memberIds[j];
        const score = kwScores[a]?.[b] ?? kwScores[b]?.[a] ?? null;
        if (score !== null) pairs.push({ a, b, score });
      }
    }

    if (pairs.length === 0) continue;

    // 模糊地带：任意一对在 0.3~0.6 之间 → 不触发
    const hasFuzzy = pairs.some((p) => p.score >= THRESHOLDS.SKW_GAP && p.score < THRESHOLDS.SKW_CLOSE);
    if (hasFuzzy) continue;

    // 有没有任意两人 < 0.3
    const hasGap = pairs.some((p) => p.score < THRESHOLDS.SKW_GAP);
    if (!hasGap) continue;

    // 判断推给谁
    const targetUsers = resolveInfoGapTargets(memberIds, pairs);
    if (targetUsers.length === 0) continue;

    const minScore = Math.min(...pairs.map((p) => p.score));
    logger.info(`[信息缺口] 关键词「${keyword}」skw_min=${minScore.toFixed(3)} → 推给 ${targetUsers.join(',')}`);

    triggers.push({
      type: 'info_gap',
      keyword,
      skwScore: minScore,
      targetUsers,
      triggerMetrics: {
        keyword,
        skw_scores: Object.fromEntries(pairs.map((p) => [`${p.a}_${p.b}`, p.score])),
      },
    });
  }

  return triggers;
}

/** 根据 pair 分布决定信息缺口推给谁 */
function resolveInfoGapTargets(
  memberIds: string[],
  pairs: Array<{ a: string; b: string; score: number }>,
): string[] {
  // 三人情形：找是否存在两人接近(>0.6)、第三人孤立(<0.3 with both)
  if (memberIds.length === 3) {
    const [u0, u1, u2] = memberIds;
    const score = (a: string, b: string) =>
      pairs.find((p) => (p.a === a && p.b === b) || (p.a === b && p.b === a))?.score ?? null;

    const candidates: Array<{ isolated: string; close: [string, string] }> = [
      { isolated: u2, close: [u0, u1] },
      { isolated: u1, close: [u0, u2] },
      { isolated: u0, close: [u1, u2] },
    ];

    for (const { isolated, close } of candidates) {
      const closeScore  = score(close[0], close[1]);
      const iso0        = score(isolated, close[0]);
      const iso1        = score(isolated, close[1]);
      if (
        closeScore !== null && closeScore > THRESHOLDS.SKW_CLOSE &&
        iso0 !== null && iso0 < THRESHOLDS.SKW_GAP &&
        iso1 !== null && iso1 < THRESHOLDS.SKW_GAP
      ) {
        return [isolated];
      }
    }

    // 三人两两均 < 0.3
    const allGap = pairs.every((p) => p.score < THRESHOLDS.SKW_GAP);
    if (allGap) return memberIds;
  }

  // 两人情形或其他：直接判断是否有 gap
  const allGap = pairs.every((p) => p.score < THRESHOLDS.SKW_GAP);
  if (allGap) return memberIds;

  return [];
}
