import { createClient } from 'redis';

type RedisClient = ReturnType<typeof createClient>;
let clientPromise: Promise<RedisClient | null> | null = null;

function getRedisUrl(): string {
  return process.env.REDIS_URL?.trim() ?? '';
}

export async function getRedisClient(): Promise<RedisClient | null> {
  if (clientPromise) {
    return clientPromise;
  }

  clientPromise = (async () => {
    const redisUrl = getRedisUrl();
    if (!redisUrl) {
      return null;
    }

    const client = createClient({ url: redisUrl });
    client.on('error', () => {
      // Keep the cache layer non-fatal; callers will fall back to DB later.
    });
    await client.connect();
    return client;
  })().catch(() => null);

  return clientPromise;
}
