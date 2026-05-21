import { createLogger } from './logger';
import { config } from './config';
import { getOngoingSessions } from './db/queries';
import { SessionWorker } from './session-worker';
import type { VadSilenceEvent } from './vad-silence-listener';

const logger = createLogger('session-manager');

export class SessionManager {
  private workers = new Map<string, SessionWorker>();
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  start(): void {
    logger.info('SessionManager starting');
    // 立即执行一次，再按周期轮询
    void this.sync();
    this.pollTimer = setInterval(() => {
      void this.sync();
    }, config.agent.sessionPollMs);
  }

  stop(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    for (const [sessionId, worker] of this.workers) {
      worker.stop();
      logger.info('Worker unregistered on shutdown', { sessionId });
    }
    this.workers.clear();
    logger.info('SessionManager stopped');
  }

  triggerVadSilence(event: VadSilenceEvent): void {
    const sessionId = event.session_id;
    const worker = this.workers.get(sessionId);
    if (!worker) {
      logger.debug('VAD silence event ignored because worker is not registered', { sessionId });
      return;
    }

    worker.onVadSilenceAvailable(event);
  }

  // ── 同步 ongoing sessions ─────────────────────────────────────────────────

  private async sync(): Promise<void> {
    try {
      const ongoingSessions = await getOngoingSessions();
      const ongoingIds = new Set(ongoingSessions.map((s) => s.id));

      // 注册新 session
      for (const session of ongoingSessions) {
        if (!this.workers.has(session.id)) {
          const sessionStartedAt = session.started_at ?? new Date();
          const worker = new SessionWorker(session.id, sessionStartedAt);
          this.workers.set(session.id, worker);
          worker.start();
          logger.info('Worker registered', {
            sessionId: session.id,
            session_started_at: sessionStartedAt.toISOString(),
            started_at_missing: session.started_at == null,
          });
        }
      }

      // 注销已结束的 session
      for (const [sessionId, worker] of this.workers) {
        if (!ongoingIds.has(sessionId)) {
          worker.stop();
          this.workers.delete(sessionId);
          logger.info('Worker unregistered', { sessionId });
        }
      }
    } catch (err) {
      logger.error('sync failed', { message: (err as Error).message });
    }
  }
}
