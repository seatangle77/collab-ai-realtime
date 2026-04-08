import { createLogger } from './logger';
import { config } from './config';
import {
  getSessionMembers,
  getLastSpeakEndGlobal,
  getLastSummary,
  getTranscriptsInWindowPreferCache,
} from './db/queries';
import { runPerceptionPipeline } from './skills/run-perception-pipeline';
import { runReasoningLayer } from './skills/run-reasoning-layer';
import { runActionLayer } from './skills/run-action-layer';
import { runSummary } from './skills/run-summary';
import { computeHasReasoning } from './skills/perception/reasoning';

const logger = createLogger('session-worker');

export class SessionWorker {
  private readonly sessionId: string;
  private shortTimer: ReturnType<typeof setInterval> | null = null;
  private analysisTimer: ReturnType<typeof setTimeout> | null = null;
  private summaryTimer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private static readonly SUMMARY_LEAD_MS = 15_000;

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

    // 摘要链提前 15s 启动，尽量在分析前产出最新上下文。
    this.scheduleSummaryTimer(
      Math.max(0, config.agent.longIntervalMs - SessionWorker.SUMMARY_LEAD_MS),
    );
    // 完整分析链保持原 120s 周期。
    this.scheduleAnalysisTimer(config.agent.longIntervalMs);
  }

  private scheduleAnalysisTimer(delayMs: number): void {
    if (!this.running) return;
    this.analysisTimer = setTimeout(() => {
      void this.runAnalysisPipeline()
        .finally(() => this.scheduleAnalysisTimer(config.agent.longIntervalMs));
    }, delayMs);
  }

  private scheduleSummaryTimer(delayMs: number): void {
    if (!this.running) return;
    this.summaryTimer = setTimeout(() => {
      void this.runSummaryPipeline()
        .finally(() => this.scheduleSummaryTimer(config.agent.longIntervalMs));
    }, delayMs);
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;

    if (this.shortTimer !== null) {
      clearInterval(this.shortTimer);
      this.shortTimer = null;
    }
    if (this.analysisTimer !== null) {
      clearTimeout(this.analysisTimer);
      this.analysisTimer = null;
    }
    if (this.summaryTimer !== null) {
      clearTimeout(this.summaryTimer);
      this.summaryTimer = null;
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

  private async runAnalysisPipeline(): Promise<void> {
    try {
      const members = await getSessionMembers(this.sessionId);
      const memberIds = members.map((m) => m.user_id);
      if (memberIds.length === 0) return;

      const windowEnd = new Date();
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);
      const startedAt = Date.now();
      logger.info('analysis pipeline started', {
        sessionId: this.sessionId,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        member_count: memberIds.length,
      });

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

      // hasReasoning（Qwen）后台异步，不阻塞主流程
      void computeHasReasoning(this.sessionId, windowStart, windowEnd, memberIds).catch((err) => {
        logger.error('hasReasoning failed', { sessionId: this.sessionId, message: (err as Error).message });
      });

      // Step3：读当前摘要与本轮发言（行动层 Prompt 需要）
      const summaryRow = await getLastSummary(this.sessionId);
      const summaryText = summaryRow?.content ?? '';
      const transcripts = await getTranscriptsInWindowPreferCache(this.sessionId, windowStart, windowEnd);

      // Step4：行动层单独执行；摘要改由独立定时链负责。
      void runActionLayer({
        sessionId: this.sessionId,
        triggers,
        windowStart,
        memberIds,
        summaryText,
        transcripts,
      }).catch((err) => {
        logger.error('action failed', {
          sessionId: this.sessionId,
          message: (err as Error).message,
        });
      });

      logger.info('analysis pipeline finished', {
        sessionId: this.sessionId,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        duration_ms: Date.now() - startedAt,
        trigger_count: triggers.length,
      });
    } catch (err) {
      logger.error('runAnalysisPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }

  private async runSummaryPipeline(): Promise<void> {
    try {
      const windowEnd = new Date();
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);
      const startedAt = Date.now();
      logger.info('summary pipeline started', {
        sessionId: this.sessionId,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
      });
      await runSummary(this.sessionId, windowStart, windowEnd);
      logger.info('summary pipeline finished', {
        sessionId: this.sessionId,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        duration_ms: Date.now() - startedAt,
      });
    } catch (err) {
      logger.error('runSummaryPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }
}
