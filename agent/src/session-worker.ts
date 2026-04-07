import { createLogger } from './logger';
import { config } from './config';
import {
  getSessionMembers,
  getLastSpeakEndGlobal,
  getLastSummary,
  getTranscriptsInWindow,
} from './db/queries';
import { runPerceptionPipeline } from './skills/run-perception-pipeline';
import { runReasoningLayer } from './skills/run-reasoning-layer';
import { runActionLayer } from './skills/run-action-layer';
import { runSummary } from './skills/run-summary';

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
      if (memberIds.length === 0) return;

      const windowEnd = new Date();
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);

      // Step1：感知层
      const result = await runPerceptionPipeline({
        sessionId: this.sessionId,
        memberIds,
        windowStart,
        windowEnd,
      });

      // Step2：推理层
      if (!result) return;
      const triggers = runReasoningLayer(result, memberIds);

      // Step3：读当前摘要与本轮发言（行动层 Prompt 需要）
      const summaryRow = await getLastSummary(this.sessionId);
      const summaryText = summaryRow?.content ?? '';
      const transcripts = await getTranscriptsInWindow(this.sessionId, windowStart, windowEnd);

      // Step4：行动层
      await runActionLayer({
        sessionId: this.sessionId,
        triggers,
        windowStart,
        memberIds,
        summaryText,
        transcripts,
      });

      // Step5：摘要层
      await runSummary(this.sessionId, windowStart, windowEnd);
    } catch (err) {
      logger.error('runFullPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }
}
