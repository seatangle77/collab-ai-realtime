import * as queries from '../src/db/queries';
import * as transcriptCache from '../src/cache/transcript-cache';
import { pool } from '../src/db/client';

describe('getTranscriptsInWindowPreferCache', () => {
  const sessionId = 's1';
  const windowStart = new Date('2026-04-08T12:00:00Z');
  const windowEnd = new Date('2026-04-08T12:02:00Z');

  beforeEach(() => {
    jest.restoreAllMocks();
  });

  it('uses cache result when cache has rows', async () => {
    jest.spyOn(transcriptCache, 'getCachedTranscriptsInWindow').mockResolvedValue([
      {
        transcript_id: 't1',
        user_id: 'u1',
        text: 'hello',
        start: new Date('2026-04-08T12:00:00Z'),
        end: new Date('2026-04-08T12:00:02Z'),
        duration: 2,
      },
    ]);
    const dbSpy = jest.spyOn(queries, 'getTranscriptsInWindow').mockResolvedValue([]);

    const rows = await queries.getTranscriptsInWindowPreferCache(sessionId, windowStart, windowEnd);

    expect(rows).toHaveLength(1);
    expect(rows[0].transcript_id).toBe('t1');
    expect(dbSpy).not.toHaveBeenCalled();
  });

  it('falls back to db when cache is empty', async () => {
    jest.spyOn(transcriptCache, 'getCachedTranscriptsInWindow').mockResolvedValue([]);
    const querySpy = jest.spyOn(pool, 'query').mockResolvedValue({
      rows: [
        {
          transcript_id: 't_db',
          user_id: 'u2',
          text: 'from-db',
          start: new Date('2026-04-08T12:01:00Z'),
          end: new Date('2026-04-08T12:01:02Z'),
          duration: 2,
        },
      ],
    } as never);

    const rows = await queries.getTranscriptsInWindowPreferCache(sessionId, windowStart, windowEnd);

    expect(rows).toHaveLength(1);
    expect(rows[0].transcript_id).toBe('t_db');
    expect(querySpy).toHaveBeenCalled();
  });

  it('falls back to db when cache reader returns empty because of extreme failure conditions', async () => {
    jest.spyOn(transcriptCache, 'getCachedTranscriptsInWindow').mockResolvedValue([]);
    jest.spyOn(pool, 'query').mockResolvedValue({
      rows: [
        {
          transcript_id: 't_edge',
          user_id: null,
          text: '',
          start: new Date('2026-04-08T12:01:30Z'),
          end: new Date('2026-04-08T12:01:30Z'),
          duration: null,
        },
      ],
    } as never);

    const rows = await queries.getTranscriptsInWindowPreferCache(sessionId, windowStart, windowEnd);

    expect(rows[0]).toMatchObject({ transcript_id: 't_edge', user_id: null, text: '' });
  });
});
