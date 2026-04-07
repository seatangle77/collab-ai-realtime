import { createLogger } from '../logger';
import {
  getTranscriptsInWindow,
  getLastSummary,
  writeDiscussionSummary,
} from '../db/queries';
import { generateSummary } from '../http/nlp-client';

const logger = createLogger('summary');

export async function runSummary(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
): Promise<string> {
  // Step1：读本轮发言
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);
  const valid = transcripts.filter((t) => t.text && t.text.trim());

  if (valid.length === 0) {
    logger.info('摘要层：本轮无发言，跳过', { sessionId });
    return '';
  }

  // Step2：读上一轮摘要
  const lastSummary = await getLastSummary(sessionId);
  const prevSummary = lastSummary?.summary_text ?? '';

  // Step3：调 Qwen 生成摘要
  const items = valid.map((t) => ({ user_id: t.user_id ?? '未知', text: t.text! }));
  const summaryText = await generateSummary(items, prevSummary);

  if (!summaryText) {
    logger.error('摘要层：Qwen 返回为空，跳过写库', { sessionId });
    return '';
  }

  // Step4：写库
  await writeDiscussionSummary({
    session_id: sessionId,
    summary_text: summaryText,
    window_start: windowStart,
    window_end: windowEnd,
  });

  logger.info(`摘要层完成 ${summaryText.length}字`, { sessionId, preview: summaryText.slice(0, 40) });
  return summaryText;
}
