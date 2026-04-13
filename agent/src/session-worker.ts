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
import { runPushDispatcher } from './skills/run-push-dispatcher';
import { runSummary } from './skills/run-summary';
import { computeHasReasoning } from './skills/perception/reasoning';
import { notifyGroupSilence } from './http/nlp-client';

const logger = createLogger('session-worker');
const GROUP_SILENCE_THRESHOLD_S = 30;
const GROUP_SILENCE_FIXED_CONTENT = '小组已沉默超过30秒，大家可以继续讨论～';

function buildRunId(kind: 'summary' | 'reasoning', sessionId: string, windowStart: Date): string {
  return `${kind}:${sessionId}:${windowStart.toISOString()}`;
}

export class SessionWorker {
  private readonly sessionId: string;
  private readonly sessionStartedAt: Date;
  private shortTimer: ReturnType<typeof setTimeout> | null = null;
  private analysisTimer: ReturnType<typeof setTimeout> | null = null;
  private summaryTimer: ReturnType<typeof setTimeout> | null = null;
  private dispatchTimer: ReturnType<typeof setInterval> | null = null;
  private lastGroupSilenceTriggerAt: number | null = null;
  private running = false;
  private static readonly SUMMARY_LEAD_MS = 15_000;
  private static readonly DISPATCH_INTERVAL_MS = 5_000;

  constructor(sessionId: string, sessionStartedAt: Date) {
    this.sessionId = sessionId;
    this.sessionStartedAt = sessionStartedAt;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    logger.info('Worker started', {
      sessionId: this.sessionId,
      session_started_at: this.sessionStartedAt.toISOString(),
    });

    // 三条时钟都锚定到会话开始时间，而不是 Worker 实际启动时间。
    this.scheduleSilenceTimer();
    this.scheduleSummaryTimer();
    this.scheduleAnalysisTimer();
    this.startDispatchLoop();
  }

  private scheduleSilenceTimer(): void {
    if (!this.running) return;
    const scheduledFor = this.nextAlignedAt(config.agent.shortIntervalMs, config.agent.shortIntervalMs);
    this.shortTimer = setTimeout(() => {
      void this.checkGroupSilence(scheduledFor)
        .finally(() => this.scheduleSilenceTimer());
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private scheduleAnalysisTimer(): void {
    if (!this.running) return;
    const scheduledFor = this.nextAlignedAt(config.agent.longIntervalMs, config.agent.longIntervalMs);
    this.analysisTimer = setTimeout(() => {
      void this.runAnalysisPipeline(scheduledFor)
        .finally(() => this.scheduleAnalysisTimer());
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private scheduleSummaryTimer(): void {
    if (!this.running) return;
    const firstOffset = Math.max(0, config.agent.longIntervalMs - SessionWorker.SUMMARY_LEAD_MS);
    const scheduledFor = this.nextAlignedAt(firstOffset, config.agent.longIntervalMs);
    this.summaryTimer = setTimeout(() => {
      void this.runSummaryPipeline(scheduledFor)
        .finally(() => this.scheduleSummaryTimer());
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private nextAlignedAt(firstOffsetMs: number, intervalMs: number): Date {
    const baseMs = this.sessionStartedAt.getTime() + firstOffsetMs;
    const nowMs = Date.now();
    if (nowMs <= baseMs) {
      return new Date(baseMs);
    }

    const elapsedSinceBase = nowMs - baseMs;
    const intervalsPassed = Math.ceil(elapsedSinceBase / intervalMs);
    return new Date(baseMs + intervalsPassed * intervalMs);
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;

    if (this.shortTimer !== null) {
      clearTimeout(this.shortTimer);
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
    if (this.dispatchTimer !== null) {
      clearInterval(this.dispatchTimer);
      this.dispatchTimer = null;
    }

    logger.info('Worker stopped', { sessionId: this.sessionId });
  }

  private startDispatchLoop(): void {
    if (!this.running || this.dispatchTimer !== null) return;

    this.dispatchTimer = setInterval(() => {
      void runPushDispatcher(this.sessionId).catch((err) => {
        logger.error('runPushDispatcher failed', {
          sessionId: this.sessionId,
          message: (err as Error).message,
        });
      });
    }, SessionWorker.DISPATCH_INTERVAL_MS);
  }

  // ── 30s：群体沉默检测 ────────────────────────────────────────────────────────

  private async checkGroupSilence(scheduledFor: Date): Promise<void> {
    try {
      const lastEnd = await getLastSpeakEndGlobal(this.sessionId);
      if (!lastEnd) return;

      const silenceMs = Date.now() - lastEnd.getTime();
      const silenceS = silenceMs / 1000;

      if (silenceS > GROUP_SILENCE_THRESHOLD_S) {
        if (!this.canTriggerGroupSilenceNow(Date.now())) {
          logger.info('Group silence detected but in cooldown', {
            sessionId: this.sessionId,
            scheduled_for: scheduledFor.toISOString(),
            silence_s: Math.round(silenceS),
          });
          return;
        }

        const sent = await notifyGroupSilence(this.sessionId, GROUP_SILENCE_FIXED_CONTENT);
        if (sent) {
          this.markGroupSilenceTriggered(Date.now());
        }

        logger.info('Group silence detected', {
          sessionId: this.sessionId,
          scheduled_for: scheduledFor.toISOString(),
          silence_s: Math.round(silenceS),
          notified: sent,
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

  private async runAnalysisPipeline(scheduledFor: Date): Promise<void> {
    try {
      const members = await getSessionMembers(this.sessionId);
      const memberIds = members.map((m) => m.user_id);
      if (memberIds.length === 0) return;

      const windowEnd = scheduledFor;
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);
      const startedAt = Date.now();
      const runId = buildRunId('reasoning', this.sessionId, windowStart);
      logger.info('===== reasoning run begin =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
      });
      logger.info('analysis pipeline started', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        actual_started_at: new Date(startedAt).toISOString(),
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
      let triggers = runReasoningLayer(result, memberIds);

      if (triggers.some((trigger) => trigger.type === 'group_silence') && !this.canTriggerGroupSilenceNow(Date.now())) {
        triggers = triggers.filter((trigger) => trigger.type !== 'group_silence');
        logger.info('analysis group_silence skipped by cooldown gate', {
          sessionId: this.sessionId,
          scheduled_for: scheduledFor.toISOString(),
        });
      }

      // hasReasoning（Qwen）后台异步，不阻塞主流程
      void computeHasReasoning(this.sessionId, windowStart, windowEnd, memberIds).catch((err) => {
        logger.error('hasReasoning failed', { sessionId: this.sessionId, message: (err as Error).message });
      });

      // Step3：读当前摘要与本轮发言（行动层 Prompt 需要）
      const summaryRow = await getLastSummary(this.sessionId);
      const summaryText = summaryRow?.content ?? '';
      const transcripts = await getTranscriptsInWindowPreferCache(this.sessionId, windowStart, windowEnd);
      const summaryKeywords = extractSummaryKeywords(summaryText);
      const focusedTranscripts = filterTranscriptsBySummaryFocus(transcripts, summaryKeywords);

      // Step4：行动层单独执行；摘要改由独立定时链负责。
      void runActionLayer({
        sessionId: this.sessionId,
        triggers,
        windowStart,
        memberIds,
        summaryText,
        transcripts: focusedTranscripts,
        onGroupSilenceNotified: () => this.markGroupSilenceTriggered(Date.now()),
      }).catch((err) => {
        logger.error('action failed', {
          sessionId: this.sessionId,
          message: (err as Error).message,
        });
      });

      logger.info('analysis pipeline finished', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        actual_finished_at: new Date().toISOString(),
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        duration_ms: Date.now() - startedAt,
        trigger_count: triggers.length,
      });
      logger.info('===== reasoning run end =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
      });
    } catch (err) {
      logger.error('runAnalysisPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }

  private async runSummaryPipeline(scheduledFor: Date): Promise<void> {
    try {
      const windowEnd = scheduledFor;
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);
      const startedAt = Date.now();
      const runId = buildRunId('summary', this.sessionId, windowStart);
      logger.info('===== summary run begin =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
      });
      logger.info('summary pipeline started', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        actual_started_at: new Date(startedAt).toISOString(),
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
      });
      await runSummary(this.sessionId, windowStart, windowEnd);
      logger.info('summary pipeline finished', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        actual_finished_at: new Date().toISOString(),
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        duration_ms: Date.now() - startedAt,
      });
      logger.info('===== summary run end =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
      });
    } catch (err) {
      logger.error('runSummaryPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }

  private canTriggerGroupSilenceNow(nowMs: number): boolean {
    if (this.lastGroupSilenceTriggerAt === null) {
      return true;
    }
    return nowMs - this.lastGroupSilenceTriggerAt >= config.agent.longIntervalMs;
  }

  private markGroupSilenceTriggered(nowMs: number): void {
    this.lastGroupSilenceTriggerAt = nowMs;
  }
}

function extractSummaryKeywords(summaryText: string): string[] {
  if (!summaryText.trim()) return [];

  const structuralWords = new Set([
    '当前讨论主题',
    '已提出的主要观点',
    '主要观点',
    '各成员的主要立场',
    '主要立场',
    '当前讨论进展与焦点',
    '讨论',
    '成员',
    '观点',
    '焦点',
    '主题',
    '当前',
  ]);

  return Array.from(
    new Set(
      summaryText
        .split(/[\s,，。；：:、!！?？()\[\]【】\-]+/)
        .map((token) => token.trim())
        .filter((token) => token.length >= 2 && !structuralWords.has(token)),
    ),
  ).slice(0, 12);
}

function filterTranscriptsBySummaryFocus(
  transcripts: Awaited<ReturnType<typeof getTranscriptsInWindowPreferCache>>,
  keywords: string[],
) {
  if (transcripts.length === 0 || keywords.length === 0) return transcripts;

  const filtered = transcripts.filter((item) => {
    const text = item.text?.trim() ?? '';
    return text && keywords.some((keyword) => text.includes(keyword));
  });

  return filtered.length > 0 ? filtered : transcripts;
}
