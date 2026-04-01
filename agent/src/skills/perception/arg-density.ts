import { getTranscriptsInWindow } from '../../db/queries';
import { segment } from '../../http/nlp-client';

export interface ArgDensityResult {
  /** user_id → arg_density (0~1)，无发言为 null */
  argDensities: Record<string, number | null>;
}

/**
 * arg_density_i = 论证词数 / 总词数
 * /nlp/segment 直接返回 arg_density，与 TTR 同一次调用可复用
 * 这里单独封装供 pipeline 按需调用
 */
export async function computeArgDensity(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<ArgDensityResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  const textByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textByUser[uid] = [];

  for (const t of transcripts) {
    if (t.user_id && t.text) {
      textByUser[t.user_id].push(t.text);
    }
  }

  const argDensities: Record<string, number | null> = {};

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const combined = textByUser[uid].join(' ').trim();
      if (!combined) {
        argDensities[uid] = null;
        return;
      }
      const result = await segment(combined);
      argDensities[uid] = result.arg_density;
    }),
  );

  for (const uid of memberIds) {
    if (!(uid in argDensities)) argDensities[uid] = null;
  }

  return { argDensities };
}
