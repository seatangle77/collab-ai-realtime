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

  it('uses cache result when cache has rows and db id list matches', async () => {
    const cached = {
      transcript_id: 't1',
      user_id: 'u1',
      speaker_name: null,
      text: 'hello',
      start: new Date('2026-04-08T12:00:00Z'),
      end: new Date('2026-04-08T12:00:02Z'),
      duration: 2,
    };
    jest.spyOn(transcriptCache, 'getCachedTranscriptsInWindow').mockResolvedValue([cached]);
    // getTranscriptsInWindowPreferCache 在 queries 模块内部直接调用 getTranscriptsInWindow，
    // jest.spyOn(queries, 'getTranscriptsInWindow') 无法替换该内部引用，须 mock pool.query。
    const querySpy = jest.spyOn(pool, 'query').mockResolvedValue({ rows: [{ ...cached }] } as never);

    const rows = await queries.getTranscriptsInWindowPreferCache(sessionId, windowStart, windowEnd);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toBe(cached);
    expect(querySpy).toHaveBeenCalled();
  });

  it('falls back to db when cache is empty', async () => {
    jest.spyOn(transcriptCache, 'getCachedTranscriptsInWindow').mockResolvedValue([]);
    const querySpy = jest.spyOn(pool, 'query').mockResolvedValue({
      rows: [
        {
          transcript_id: 't_db',
          user_id: 'u2',
          speaker_name: null,
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
          speaker_name: null,
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
