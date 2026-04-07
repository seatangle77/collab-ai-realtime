import { getTranscriptsInWindow } from '../../db/queries';
import { embed, similarity } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:srep');

export interface SrepResult {
  /** user_id → srep (0~1)，utterance 数 < 2 则为 null */
  sreps: Record<string, number | null>;
}

/**
 * S_rep_i = 用户本窗口内各话语 embedding 的两两余弦相似度均值
 * 高 Srep 表示内容重复，低 Srep 表示内容多样
 * utterance 数 < 2 时无法计算，置 null
 */
export async function computeSrep(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<SrepResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  const utterancesByUser: Record<string, string[]> = {};
  for (const uid of memberIds) utterancesByUser[uid] = [];

  for (const t of transcripts) {
    if (t.user_id && t.text && t.user_id in utterancesByUser) {
      utterancesByUser[t.user_id].push(t.text);
    }
  }

  const sreps: Record<string, number | null> = {};

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const utterances = utterancesByUser[uid];
      if (utterances.length < 2) {
        sreps[uid] = null;
        return;
      }

      logger.info(`[语义重复度 Srep] 正在向量化用户 ${uid} 的 ${utterances.length} 条发言`, { sessionId });
      const embeddings = await embed(utterances);
      logger.info(`[语义重复度 Srep] 向量化完成，计算相邻发言间余弦相似度`, { sessionId, uid });

      // 构建所有相邻 pair
      const pairs: Array<{ vec_a: number[]; vec_b: number[] }> = [];
      for (let i = 0; i < embeddings.length - 1; i++) {
        pairs.push({ vec_a: embeddings[i], vec_b: embeddings[i + 1] });
      }

      const scores = await similarity(pairs);
      const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
      sreps[uid] = avg;
      const level = avg >= 0.85 ? '高（内容重复）' : avg >= 0.6 ? '中' : '低（内容多样）';
      logger.info(`[语义重复度 Srep] 用户 ${uid} 结果：Srep=${avg.toFixed(3)}（${level}），基于 ${scores.length} 对相邻发言`, { sessionId });
    }),
  );

  for (const uid of memberIds) {
    if (!(uid in sreps)) sreps[uid] = null;
  }

  return { sreps };
}
