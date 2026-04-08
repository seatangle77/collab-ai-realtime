import { createLogger } from '../logger';
import { getTranscriptsInWindowPreferCache, getLastSummary } from '../db/queries';
import { generateSummary, notifySummary } from '../http/nlp-client';

const logger = createLogger('summary');

export async function runSummary(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
): Promise<string> {
  // Step1：读本轮发言
  const transcripts = await getTranscriptsInWindowPreferCache(sessionId, windowStart, windowEnd);
  const valid = transcripts.filter((t) => t.text && t.text.trim());

  if (valid.length === 0) {
    logger.info('摘要层：本轮无发言，跳过', { sessionId });
    return '';
  }

  // Step2：读上一轮摘要
  const lastSummary = await getLastSummary(sessionId);
  const prevSummary = lastSummary?.content ?? '';

  // Step3：调 Qwen 生成摘要
  const items = valid.map((t) => ({ user_id: t.user_id ?? '未知', text: t.text! }));
  const summaryText = await generateSummary(items, prevSummary);

  if (!summaryText) {
    logger.error('摘要层：Qwen 返回为空，跳过写库', { sessionId });
    return '';
  }

  // Step4：提交后端写库并广播
  try {
    await notifySummary(sessionId, summaryText, windowStart, windowEnd);
    logger.info(`摘要层完成 ${summaryText.length}字`, { sessionId, preview: summaryText.slice(0, 40) });
  } catch (err) {
    logger.error('摘要层：写库/广播失败，本轮摘要未持久化', { sessionId, message: (err as Error).message });
    return '';
  }
  return summaryText;
}
