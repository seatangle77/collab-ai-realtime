import { getTranscriptsInWindow } from '../../db/queries';
import { reasoningBatch } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:reasoning');

export interface ReasoningResult {
  hasReasoningMap: Record<string, boolean | null>;
  hasEvidenceMap: Record<string, boolean | null>;
  reasoningSourceMap: Record<string, string | null>;
  evidenceSourceMap: Record<string, string | null>;
}

/**
 * 全员批量论证结构判定（fast_model，一次调用返回全组四字段结果）。
 * 无发言的成员直接填 null，不进入 LLM。
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
  const reasoningSourceMap: Record<string, string | null> = {};
  const evidenceSourceMap: Record<string, string | null> = {};

  for (const uid of memberIds) {
    hasReasoningMap[uid] = null;
    hasEvidenceMap[uid] = null;
    reasoningSourceMap[uid] = null;
    evidenceSourceMap[uid] = null;
  }

  const batchInput = memberIds
    .map((uid) => ({ user_id: uid, text: textByUser[uid].join(' ').trim() }))
    .filter((m) => m.text.length > 0);

  if (batchInput.length === 0) {
    logger.info('[论证检测] 本轮全员无发言，跳过批量判定', { sessionId });
    return { hasReasoningMap, hasEvidenceMap, reasoningSourceMap, evidenceSourceMap };
  }

  logger.info(`[论证检测] 批量判定 成员数=${batchInput.length}`, { sessionId });
  const results = await reasoningBatch(batchInput);

  for (const r of results) {
    hasReasoningMap[r.user_id] = r.reasoning_status;
    hasEvidenceMap[r.user_id] = r.evidence_status;
    reasoningSourceMap[r.user_id] = r.reasoning_source;
    evidenceSourceMap[r.user_id] = r.evidence_source;

    const rsn = r.reasoning_status ? '✅ 含论证' : '❌ 无论证';
    const evi = r.evidence_status ? '✅ 有证据' : '❌ 无证据';
    logger.info(
      `[论证检测] 用户 ${r.user_id} 结果：${rsn}（${r.reasoning_source}），${evi}（${r.evidence_source}）`,
      { sessionId },
    );
  }

  return { hasReasoningMap, hasEvidenceMap, reasoningSourceMap, evidenceSourceMap };
}
