import { getTranscriptsInWindow } from '../../db/queries';
import { hasReasoning } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:reasoning');

export interface ReasoningResult {
  /** user_id → has_reasoning，无发言为 null */
  hasReasoningMap: Record<string, boolean | null>;
  /** user_id → has_evidence，无发言为 null */
  hasEvidenceMap: Record<string, boolean | null>;
}

/**
 * 对每位用户的合并发言调用 /api/nlp/has_reasoning（背后由 Qwen 判断）
 * 返回该用户是否含论证结构（has_reasoning）以及是否引用了证据（has_evidence）
 */
export async function computeHasReasoning(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<ReasoningResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  const textByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textByUser[uid] = [];

  for (const t of transcripts) {
    if (t.user_id && t.text && t.user_id in textByUser) {
      textByUser[t.user_id].push(t.text);
    }
  }

  const hasReasoningMap: Record<string, boolean | null> = {};
  const hasEvidenceMap: Record<string, boolean | null> = {};

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const combined = textByUser[uid].join(' ').trim();
      if (!combined) {
        hasReasoningMap[uid] = null;
        hasEvidenceMap[uid] = null;
        return;
      }

      logger.info(`[论证检测 Qwen] 正在分析用户 ${uid} 的发言是否含论证结构（${combined.length} 字）`, { sessionId });
      const result = await hasReasoning(combined);
      hasReasoningMap[uid] = result.has_reasoning;
      hasEvidenceMap[uid] = result.has_evidence;

      const reasoningLabel = result.has_reasoning ? '✅ 含论证' : '❌ 无论证';
      const evidenceLabel = result.has_evidence ? '✅ 有引用证据' : '❌ 无证据引用';
      const methodLabel = result.method === 'llm' ? '（Qwen 判断）' : '（关键词规则）';
      logger.info(`[论证检测 Qwen] 用户 ${uid} 结果：${reasoningLabel}，${evidenceLabel} ${methodLabel}`, { sessionId });
    }),
  );

  for (const uid of memberIds) {
    if (!(uid in hasReasoningMap)) {
      hasReasoningMap[uid] = null;
      hasEvidenceMap[uid] = null;
    }
  }

  return { hasReasoningMap, hasEvidenceMap };
}
