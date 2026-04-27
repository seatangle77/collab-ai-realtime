import { getTranscriptsInWindow } from '../../db/queries';
import { segment } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:ttr-and-arg-density');

export interface TtrAndArgDensityResult {
  /** user_id → TTR (0~1)，无发言为 null */
  ttrs: Record<string, number | null>;
  /** user_id → arg_density (0~1)，无发言为 null */
  argDensities: Record<string, number | null>;
}

/**
 * 合并计算 TTR 和 arg_density，共用一次 DB 查询和一次 NLP 调用。
 *
 * TTR = unique_tokens / total_tokens（阈值：≥0.6 高，≥0.3 中，<0.3 低）
 * arg_density = 论证词数 / 总词数
 */
export async function computeTtrAndArgDensity(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<TtrAndArgDensityResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  const textByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textByUser[uid] = [];

  for (const t of transcripts) {
    if (t.user_id && t.text && t.user_id in textByUser) {
      textByUser[t.user_id].push(t.text);
    }
  }

  const ttrs: Record<string, number | null> = {};
  const argDensities: Record<string, number | null> = {};

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const combined = textByUser[uid].join(' ').trim();
      if (!combined) {
        ttrs[uid] = null;
        argDensities[uid] = null;
        return;
      }

      logger.info(`[TTR+论证密度] 正在分析用户 ${uid} 的发言（${combined.length} 字）`, { sessionId });
      const result = await segment(combined);

      ttrs[uid] = result.ttr;
      argDensities[uid] = result.arg_density;

      const ttrLevel = result.ttr >= 0.6 ? '高（词汇丰富）' : result.ttr >= 0.3 ? '中' : '低（重复较多）';
      const argLevel = result.arg_density >= 0.3 ? '高（多论证词）' : result.arg_density >= 0.1 ? '中' : '低（缺乏论证）';

      logger.info(
        `[TTR+论证密度] 用户 ${uid} | TTR=${result.ttr.toFixed(3)}（${ttrLevel}）| arg_density=${result.arg_density.toFixed(3)}（${argLevel}）`,
        { sessionId },
      );
    }),
  );

  for (const uid of memberIds) {
    if (!(uid in ttrs)) ttrs[uid] = null;
    if (!(uid in argDensities)) argDensities[uid] = null;
  }

  return { ttrs, argDensities };
}
