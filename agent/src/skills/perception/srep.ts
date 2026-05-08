import { getTranscriptsInWindow } from '../../db/queries';
import { embed } from '../../http/nlp-client';
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
  const srepItems: Array<{ userId: string; text: string }> = [];
  const utteranceCountByUser: Record<string, number> = {};

  for (const uid of memberIds) {
    let utterances = utterancesByUser[uid];
    if (utterances.length < 2) {
      const sentences = utterances.join('')
        .split(/[。！？…]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      if (sentences.length >= 2) {
        utterances = sentences;
        logger.info(`[语义重复度 Srep] 用户 ${uid} 发言不足2条，按标点切分为 ${sentences.length} 句`, { sessionId });
      } else {
        sreps[uid] = null;
        continue;
      }
    }

    utteranceCountByUser[uid] = utterances.length;
    for (const text of utterances) {
      srepItems.push({ userId: uid, text });
    }
  }

  if (srepItems.length === 0) {
    for (const uid of memberIds) {
      if (!(uid in sreps)) sreps[uid] = null;
    }
    return { sreps };
  }

  logger.info(`[语义重复度 Srep] 正在批量向量化 ${srepItems.length} 条发言，涉及 ${Object.keys(utteranceCountByUser).length} 位用户`, { sessionId });
  let allEmbeddings: number[][];
  try {
    allEmbeddings = await embed(srepItems.map((item) => item.text));
  } catch (err) {
    logger.error('[语义重复度 Srep] 批量向量化失败，本轮 Srep 全部置空', {
      sessionId,
      message: (err as Error).message,
    });
    for (const uid of memberIds) {
      if (!(uid in sreps)) sreps[uid] = null;
    }
    return { sreps };
  }

  const embeddingsByUser: Record<string, number[][]> = {};
  for (const uid of memberIds) embeddingsByUser[uid] = [];
  allEmbeddings.forEach((embedding, idx) => {
    const uid = srepItems[idx]?.userId;
    if (uid && uid in embeddingsByUser) {
      embeddingsByUser[uid].push(embedding);
    }
  });

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const embeddings = embeddingsByUser[uid] ?? [];
      if (embeddings.length < 2) {
        if (!(uid in sreps)) sreps[uid] = null;
        return;
      }
      logger.info(`[语义重复度 Srep] 向量化完成，计算两两全组合余弦相似度`, { sessionId, uid });

      const scores: number[] = [];
      for (let i = 0; i < embeddings.length - 1; i++) {
        for (let j = i + 1; j < embeddings.length; j++) {
          scores.push(cosineSimilarity(embeddings[i], embeddings[j]));
        }
      }

      const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
      sreps[uid] = avg;
      const level = avg >= 0.85 ? '高（内容重复）' : avg >= 0.6 ? '中' : '低（内容多样）';
      logger.info(`[语义重复度 Srep] 用户 ${uid} 结果：Srep=${avg.toFixed(3)}（${level}），基于 ${scores.length} 对两两组合`, { sessionId });
    }),
  );

  for (const uid of memberIds) {
    if (!(uid in sreps)) sreps[uid] = null;
  }

  return { sreps };
}

function cosineSimilarity(vecA: number[], vecB: number[]): number {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  const len = Math.min(vecA.length, vecB.length);

  for (let i = 0; i < len; i++) {
    dot += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }

  if (normA === 0 || normB === 0) return 0;
  const raw = dot / (Math.sqrt(normA) * Math.sqrt(normB));
  return Math.max(-1, Math.min(1, raw));
}
