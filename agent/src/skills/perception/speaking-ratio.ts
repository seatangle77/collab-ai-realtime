import { getTranscriptsInWindow } from '../../db/queries';

export interface SpeakingRatioResult {
  /** user_id → speaking_ratio (0~1) */
  ratios: Record<string, number>;
}

/**
 * Ri = SUM(effective_duration_i) / SUM(effective_duration_all)
 * 分母是全组实际发言总时长，全组之和 = 1，窗口内无发言的成员 ratio = 0。
 * 每条发言的有效时长只取落在窗口内的部分（只截后端：start < windowEnd 的发言才计入，
 * 结束时间超出窗口则截到 windowEnd）。
 */
export async function computeSpeakingRatio(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<SpeakingRatioResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  const durationByUser: Record<string, number> = {};
  for (const uid of memberIds) {
    durationByUser[uid] = 0;
  }

  for (const t of transcripts) {
    if (t.user_id === null) continue;
    // 只截后端：有效时长 = MIN(end, windowEnd) - start
    const effectiveDur =
      (Math.min(t.end.getTime(), windowEnd.getTime()) - t.start.getTime()) / 1000;
    if (effectiveDur <= 0) continue;
    durationByUser[t.user_id] = (durationByUser[t.user_id] ?? 0) + effectiveDur;
  }

  const totalDuration = Object.values(durationByUser).reduce((a, b) => a + b, 0);

  const ratios: Record<string, number> = {};
  if (totalDuration === 0) {
    for (const uid of memberIds) ratios[uid] = 0;
  } else {
    for (const uid of memberIds) {
      ratios[uid] = (durationByUser[uid] ?? 0) / totalDuration;
    }
  }

  return { ratios };
}
