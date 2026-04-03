import { Pool, types } from 'pg';
import { config } from '../config';
import { createLogger } from '../logger';

const logger = createLogger('db');

// timestamp without time zone (OID 1114)：pg 默认按本地时区解析，
// 但 DB 里存的是 UTC 值，直接在字符串末尾加 Z 强制当 UTC 处理，
// 避免与 JS Date.now()（UTC）比较时产生 8 小时偏移。
types.setTypeParser(1114, (str: string) => new Date(str + 'Z'));

export const pool = new Pool({
  host: config.db.host,
  port: config.db.port,
  database: config.db.database,
  user: config.db.user,
  password: config.db.password,
  max: 10,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 5_000,
});

pool.on('error', (err) => {
  logger.error('Unexpected DB pool error', { message: err.message });
});

export async function pingDb(): Promise<void> {
  const client = await pool.connect();
  try {
    await client.query('SELECT 1');
    logger.info('DB connection OK');
  } finally {
    client.release();
  }
}
