import { createLogger } from '../logger';
import type { Transcript } from '../db/queries';
import { getRedisClient } from './redis-client';

const logger = createLogger('transcript-cache');
const TRANSCRIPT_CACHE_KEY_PREFIX = 'transcript:session';

interface CachedTranscript {
  transcript_id?: string;
  user_id?: string | null;
  text?: string | null;
  start?: string;
  end?: string;
  duration?: number | null;
}

function buildCacheKey(sessionId: string): string {
  return `${TRANSCRIPT_CACHE_KEY_PREFIX}:${sessionId}`;
}

function toTimestampMs(value: Date): number {
  return value.getTime();
}

function toTranscript(item: CachedTranscript): Transcript | null {
  if (!item.transcript_id || !item.start || !item.end) {
    return null;
  }

  return {
    transcript_id: item.transcript_id,
    user_id: item.user_id ?? null,
    text: item.text ?? '',
    start: new Date(item.start),
    end: new Date(item.end),
    duration: item.duration ?? null,
  };
}

export async function getCachedTranscriptsInWindow(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
): Promise<Transcript[]> {
  const client = await getRedisClient();
  if (!client) {
    logger.info('skip transcript cache read because redis is not configured', { sessionId });
    return [];
  }

  try {
    const rows = await client.zRangeByScore(
      buildCacheKey(sessionId),
      toTimestampMs(windowStart),
      toTimestampMs(windowEnd),
    );

    const transcripts = rows
      .map((row: string) => {
        try {
          return toTranscript(JSON.parse(row) as CachedTranscript);
        } catch {
          logger.warn('cached transcript JSON parse failed', { sessionId });
          return null;
        }
      })
      .filter((item: Transcript | null): item is Transcript => item !== null);
    logger.info('read transcript cache window', {
      sessionId,
      count: transcripts.length,
      windowStart: windowStart.toISOString(),
      windowEnd: windowEnd.toISOString(),
    });
    return transcripts;
  } catch (err) {
    logger.error('read cached transcripts failed', {
      sessionId,
      message: (err as Error).message,
    });
    return [];
  }
}
