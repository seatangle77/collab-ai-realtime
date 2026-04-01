import { getTranscriptsInWindow } from '../../db/queries';
import { segment } from '../../http/nlp-client';

export interface TtrResult {
  /** user_id → TTR (0~1)，无发言为 null */
  ttrs: Record<string, number | null>;
}

/**
 * TTR_i = unique_tokens / total_tokens
 * 合并用户在窗口内所有发言后送 /nlp/segment
 */
export async function computeTtr(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<TtrResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  const textByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textByUser[uid] = [];

  for (const t of transcripts) {
    if (t.user_id && t.text) {
      textByUser[t.user_id].push(t.text);
    }
  }

  const ttrs: Record<string, number | null> = {};

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const combined = textByUser[uid].join(' ').trim();
      if (!combined) {
        ttrs[uid] = null;
        return;
      }
      const result = await segment(combined);
      ttrs[uid] = result.ttr;
    }),
  );

  // allSettled 不会抛出，对 rejected 的成员置 null
  for (const uid of memberIds) {
    if (!(uid in ttrs)) ttrs[uid] = null;
  }

  return { ttrs };
}
