import { getTranscriptsInWindow } from '../../db/queries';

export interface SpeakingRatioResult {
  /** user_id → speaking_ratio (0~1) */
  ratios: Record<string, number>;
}

/**
 * Ri = SUM(duration) / window_duration_s
 * 窗口内无发言的成员 ratio = 0
 */
export async function computeSpeakingRatio(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<SpeakingRatioResult> {
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);
  const windowDuration = (windowEnd.getTime() - windowStart.getTime()) / 1000;

  const durationByUser: Record<string, number> = {};
  for (const uid of memberIds) {
    durationByUser[uid] = 0;
  }

  for (const t of transcripts) {
    if (t.user_id === null) continue;
    const dur = t.duration ?? (t.end.getTime() - t.start.getTime()) / 1000;
    durationByUser[t.user_id] = (durationByUser[t.user_id] ?? 0) + dur;
  }

  const ratios: Record<string, number> = {};
  for (const uid of memberIds) {
    ratios[uid] = Math.min(1, (durationByUser[uid] ?? 0) / windowDuration);
  }

  return { ratios };
}
