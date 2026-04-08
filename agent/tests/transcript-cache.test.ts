import { getCachedTranscriptsInWindow } from '../src/cache/transcript-cache';

jest.mock('../src/cache/redis-client', () => ({
  getRedisClient: jest.fn(),
}));

const { getRedisClient } = jest.requireMock('../src/cache/redis-client') as {
  getRedisClient: jest.Mock;
};

describe('transcript cache reader', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('returns empty array when redis is not configured', async () => {
    getRedisClient.mockResolvedValue(null);

    await expect(
      getCachedTranscriptsInWindow('s1', new Date('2026-04-08T12:00:00Z'), new Date('2026-04-08T12:02:00Z')),
    ).resolves.toEqual([]);
  });

  it('reads valid cached rows and skips malformed or incomplete rows', async () => {
    getRedisClient.mockResolvedValue({
      zRangeByScore: jest.fn().mockResolvedValue([
        '{"transcript_id":"t1","user_id":"u1","text":"hello","start":"2026-04-08T12:00:00.000Z","end":"2026-04-08T12:00:02.000Z","duration":2}',
        'not-json',
        '{"transcript_id":"t2","user_id":"u2","text":"world","start":"2026-04-08T12:00:03.000Z","end":"2026-04-08T12:00:05.000Z","duration":2}',
        '{"user_id":"u3","text":"missing ids"}',
      ]),
    });

    const rows = await getCachedTranscriptsInWindow(
      's1',
      new Date('2026-04-08T12:00:00Z'),
      new Date('2026-04-08T12:02:00Z'),
    );

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ transcript_id: 't1', user_id: 'u1', text: 'hello' });
    expect(rows[1]).toMatchObject({ transcript_id: 't2', user_id: 'u2', text: 'world' });
  });

  it('returns empty array when redis read throws', async () => {
    getRedisClient.mockResolvedValue({
      zRangeByScore: jest.fn().mockRejectedValue(new Error('boom')),
    });

    await expect(
      getCachedTranscriptsInWindow('s1', new Date('2026-04-08T12:00:00Z'), new Date('2026-04-08T12:02:00Z')),
    ).resolves.toEqual([]);
  });
});
