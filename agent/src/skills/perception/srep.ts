import { getTranscriptsInWindow } from '../../db/queries';
import { embed, similarity } from '../../http/nlp-client';

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
    if (t.user_id && t.text) {
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

      const embeddings = await embed(utterances);

      // 构建所有相邻 pair
      const pairs: Array<{ vec_a: number[]; vec_b: number[] }> = [];
      for (let i = 0; i < embeddings.length - 1; i++) {
        pairs.push({ vec_a: embeddings[i], vec_b: embeddings[i + 1] });
      }

      const scores = await similarity(pairs);
      const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
      sreps[uid] = avg;
    }),
  );

  for (const uid of memberIds) {
    if (!(uid in sreps)) sreps[uid] = null;
  }

  return { sreps };
}
