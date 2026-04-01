import { getLastSpeakEndPerUser } from '../../db/queries';

export interface SilenceResult {
  /** user_id → silence_s (秒)，未发言则等于窗口长度 */
  silenceSeconds: Record<string, number>;
}

/**
 * Silence_i = now - MAX(end) for user i
 * 若用户在 windowStart 之后从未发言，silence = windowDuration
 */
export async function computeSilence(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<SilenceResult> {
  const now = windowEnd;
  const windowDuration = (windowEnd.getTime() - windowStart.getTime()) / 1000;

  const rows = await getLastSpeakEndPerUser(sessionId, windowStart);
  const lastEndByUser: Record<string, Date> = {};
  for (const row of rows) {
    lastEndByUser[row.user_id] = row.last_end;
  }

  const silenceSeconds: Record<string, number> = {};
  for (const uid of memberIds) {
    const lastEnd = lastEndByUser[uid];
    if (!lastEnd) {
      silenceSeconds[uid] = windowDuration;
    } else {
      silenceSeconds[uid] = Math.max(0, (now.getTime() - lastEnd.getTime()) / 1000);
    }
  }

  return { silenceSeconds };
}
