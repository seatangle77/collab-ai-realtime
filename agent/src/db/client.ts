import { Pool } from 'pg';
import { config } from '../config';
import { createLogger } from '../logger';

const logger = createLogger('db');

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
