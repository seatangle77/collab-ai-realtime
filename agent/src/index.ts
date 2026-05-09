import { pingDb } from './db/client';
import { pool } from './db/client';
import { SessionManager } from './session-manager';
import { createLogger } from './logger';
import { VadSilenceListener } from './vad-silence-listener';

const logger = createLogger('main');

async function main(): Promise<void> {
  logger.info('Agent starting');

  await pingDb();

  const manager = new SessionManager();
  manager.start();

  const vadSilenceListener = new VadSilenceListener((event) => {
    manager.triggerVadSilence(event.session_id);
  });
  await vadSilenceListener.start();

  // 优雅退出
  const shutdown = async (signal: string): Promise<void> => {
    logger.info(`Received ${signal}, shutting down`);
    await vadSilenceListener.stop();
    manager.stop();
    await pool.end();
    logger.info('Agent stopped');
    process.exit(0);
  };

  process.on('SIGINT',  () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
