import { createLogger } from './logger';
import { config } from './config';
import { getSessionMembers, getLastSpeakEndGlobal } from './db/queries';
import { runPerceptionPipeline } from './skills/run-perception-pipeline';

const logger = createLogger('session-worker');

export class SessionWorker {
  private readonly sessionId: string;
  private shortTimer: ReturnType<typeof setInterval> | null = null;
  private longTimer: ReturnType<typeof setInterval> | null = null;
  private running = false;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    logger.info('Worker started', { sessionId: this.sessionId });

    // 30s 定时器：群体沉默检测
    this.shortTimer = setInterval(() => {
      void this.checkGroupSilence();
    }, config.agent.shortIntervalMs);

    // 120s 定时器：完整感知层 pipeline
    this.longTimer = setInterval(() => {
      void this.runFullPipeline();
    }, config.agent.longIntervalMs);
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;

    if (this.shortTimer !== null) {
      clearInterval(this.shortTimer);
      this.shortTimer = null;
    }
    if (this.longTimer !== null) {
      clearInterval(this.longTimer);
      this.longTimer = null;
    }

    logger.info('Worker stopped', { sessionId: this.sessionId });
  }

  // ── 30s：群体沉默检测 ────────────────────────────────────────────────────────

  private async checkGroupSilence(): Promise<void> {
    try {
      const lastEnd = await getLastSpeakEndGlobal(this.sessionId);
      if (!lastEnd) return;

      const silenceMs = Date.now() - lastEnd.getTime();
      const silenceS = silenceMs / 1000;

      if (silenceS > 30) {
        logger.info('Group silence detected', {
          sessionId: this.sessionId,
          silence_s: Math.round(silenceS),
        });
        // Week 3 推理层在此消费此事件，目前只记录日志
      }
    } catch (err) {
      logger.error('checkGroupSilence failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }

  // ── 120s：完整感知层 pipeline ────────────────────────────────────────────────

  private async runFullPipeline(): Promise<void> {
    try {
      const members = await getSessionMembers(this.sessionId);
      const memberIds = members.map((m) => m.user_id);

      const windowEnd = new Date();
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);

      await runPerceptionPipeline({
        sessionId: this.sessionId,
        memberIds,
        windowStart,
        windowEnd,
      });
    } catch (err) {
      logger.error('runFullPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }
}
