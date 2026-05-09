import { createLogger } from './logger';
import { config } from './config';
import {
  getSessionMembers,
  getLastSpeakEndGlobal,
  getLastSummary,
  getTranscriptsInWindowPreferCache,
  writeDiscussionState,
} from './db/queries';
import { runPerceptionPipeline } from './skills/run-perception-pipeline';
import { runActionLayer } from './skills/run-action-layer';
import { runPushDispatcher } from './skills/run-push-dispatcher';
import { runSummary } from './skills/run-summary';
import {
  decideInfoGapButtons,
  recallInfoGapKeywords,
  type InfoGapKeywordCandidate,
} from './skills/info-gap';
import { generateGroupSilence, notifyGroupSilence } from './http/nlp-client';

const logger = createLogger('session-worker');
const GROUP_SILENCE_THRESHOLD_S = 30;

function buildRunId(kind: 'summary' | 'reasoning', sessionId: string, windowStart: Date): string {
  return `${kind}:${sessionId}:${windowStart.toISOString()}`;
}

export class SessionWorker {
  private readonly sessionId: string;
  private readonly sessionStartedAt: Date;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private analysisTimer: ReturnType<typeof setTimeout> | null = null;
  private infoGapTimer: ReturnType<typeof setTimeout> | null = null;
  private summaryTimer: ReturnType<typeof setTimeout> | null = null;
  private dispatchTimer: ReturnType<typeof setTimeout> | null = null;
  private infoGapCandidates: InfoGapKeywordCandidate[] = [];
  private lastGroupSilenceTriggerAt: number | null = null;
  private dispatchInFlight = false;
  private running = false;
  private static readonly SUMMARY_LEAD_MS = 15_000;
  private static readonly DISPATCH_INTERVAL_MS = 120_000;

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

    this.scheduleSilenceTimer();
    this.scheduleSummaryTimer();
    this.scheduleAnalysisTimer();
    this.scheduleInfoGapTimer();
    this.scheduleDispatchTimer();
  }

  private scheduleSilenceTimer(nextScheduledFor?: Date): void {
    if (!this.running) return;
    const scheduledFor = nextScheduledFor
      ?? this.nextAlignedAt(config.agent.silenceIntervalMs, config.agent.silenceIntervalMs);
    this.silenceTimer = setTimeout(() => {
      void this.checkGroupSilence(scheduledFor)
        .finally(() => {
          this.scheduleSilenceTimer(
            new Date(scheduledFor.getTime() + config.agent.silenceIntervalMs),
          );
        });
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private scheduleAnalysisTimer(nextScheduledFor?: Date): void {
    if (!this.running) return;
    const scheduledFor = nextScheduledFor
      ?? this.nextAlignedAt(config.agent.analysisIntervalMs, config.agent.analysisIntervalMs);
    this.analysisTimer = setTimeout(() => {
      void this.runAnalysisPipeline(scheduledFor)
        .finally(() => {
          this.scheduleAnalysisTimer(
            new Date(scheduledFor.getTime() + config.agent.analysisIntervalMs),
          );
        });
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private scheduleInfoGapTimer(nextScheduledFor?: Date): void {
    if (!this.running) return;
    const scheduledFor = nextScheduledFor
      ?? this.nextAlignedAt(config.agent.infoGapIntervalMs, config.agent.infoGapIntervalMs);
    this.infoGapTimer = setTimeout(() => {
      void this.runInfoGapPipeline(scheduledFor)
        .finally(() => {
          this.scheduleInfoGapTimer(
            new Date(scheduledFor.getTime() + config.agent.infoGapIntervalMs),
          );
        });
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private scheduleSummaryTimer(nextScheduledFor?: Date): void {
    if (!this.running) return;
    const firstOffset = Math.max(0, config.agent.longIntervalMs - SessionWorker.SUMMARY_LEAD_MS);
    const scheduledFor = nextScheduledFor
      ?? this.nextAlignedAt(firstOffset, config.agent.longIntervalMs);
    this.summaryTimer = setTimeout(() => {
      void this.runSummaryPipeline(scheduledFor)
        .finally(() => {
          this.scheduleSummaryTimer(
            new Date(scheduledFor.getTime() + config.agent.longIntervalMs),
          );
        });
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  private scheduleDispatchTimer(nextScheduledFor?: Date): void {
    if (!this.running) return;
    const scheduledFor = nextScheduledFor
      ?? this.nextAlignedAt(
        SessionWorker.DISPATCH_INTERVAL_MS,
        SessionWorker.DISPATCH_INTERVAL_MS,
      );
    this.dispatchTimer = setTimeout(() => {
      this.triggerPushDispatcher('timer')
        .finally(() => {
          this.scheduleDispatchTimer(
            new Date(scheduledFor.getTime() + SessionWorker.DISPATCH_INTERVAL_MS),
          );
        });
    }, Math.max(0, scheduledFor.getTime() - Date.now()));
  }

  onVadSilenceAvailable(): void {
    void this.triggerPushDispatcher('vad_silence');
  }

  private async triggerPushDispatcher(reason: 'timer' | 'queued' | 'vad_silence'): Promise<void> {
    if (!this.running) return;
    if (this.dispatchInFlight) {
      logger.info('runPushDispatcher skipped because previous dispatch is still running', {
        sessionId: this.sessionId,
        reason,
      });
      return;
    }

    this.dispatchInFlight = true;
    try {
      logger.info('runPushDispatcher triggered', { sessionId: this.sessionId, reason });
      await runPushDispatcher(this.sessionId);
    } catch (err) {
      logger.error('runPushDispatcher failed', {
        sessionId: this.sessionId,
        reason,
        message: (err as Error).message,
      });
    } finally {
      this.dispatchInFlight = false;
    }
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

    if (this.silenceTimer !== null) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    if (this.analysisTimer !== null) {
      clearTimeout(this.analysisTimer);
      this.analysisTimer = null;
    }
    if (this.infoGapTimer !== null) {
      clearTimeout(this.infoGapTimer);
      this.infoGapTimer = null;
    }
    if (this.summaryTimer !== null) {
      clearTimeout(this.summaryTimer);
      this.summaryTimer = null;
    }
    if (this.dispatchTimer !== null) {
      clearTimeout(this.dispatchTimer);
      this.dispatchTimer = null;
    }

    logger.info('Worker stopped', { sessionId: this.sessionId });
  }

  // ── 群体沉默检测：默认每 30s 检查一次 ───────────────────────────────────────────

  private async checkGroupSilence(scheduledFor: Date): Promise<void> {
    try {
      const lastEnd = await getLastSpeakEndGlobal(this.sessionId);
      if (!lastEnd) return;

      const silenceMs = Date.now() - lastEnd.getTime();
      const silenceS = silenceMs / 1000;

      if (silenceS <= GROUP_SILENCE_THRESHOLD_S) return;

      if (!this.canTriggerGroupSilenceNow(Date.now())) {
        logger.info('Group silence detected but in cooldown', {
          sessionId: this.sessionId,
          silence_s: Math.round(silenceS),
        });
        return;
      }

      logger.info('Group silence detected, calling fast_model', {
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        silence_s: Math.round(silenceS),
      });

      // 获取上下文：摘要 + 最近发言
      const windowEnd = new Date();
      const windowStart = new Date(windowEnd.getTime() - config.agent.longIntervalMs);
      const [summaryRow, transcripts] = await Promise.all([
        getLastSummary(this.sessionId),
        getTranscriptsInWindowPreferCache(this.sessionId, windowStart, windowEnd),
      ]);

      const summaryText = summaryRow?.content ?? '';
      const transcriptText = transcripts
        .filter((t) => t.text?.trim())
        .map((t) => `${t.speaker_name ?? t.user_id}：${t.text!.trim()}`)
        .join('\n');

      // fast_model 生成破冰话题
      const content = await generateGroupSilence({
        summary: summaryText,
        transcripts: transcriptText,
        silence_s: Math.round(silenceS),
      });

      const finalContent = content.trim() || '大家聊聊目前最关心的是哪个方面？';

      // anchor = 沉默前最后一条发言
      const lastTranscript = transcripts.length > 0 ? transcripts[transcripts.length - 1] : null;

      // 广播给全组
      const sent = await notifyGroupSilence(this.sessionId, finalContent);
      if (sent) {
        this.markGroupSilenceTriggered(Date.now());
        logger.info(`group_silence 广播成功，内容="${finalContent}"`, { sessionId: this.sessionId });
      }

      // 写 discussion_states 记录
      void writeDiscussionState({
        session_id: this.sessionId,
        state_type: 'group_silence',
        trigger_metrics: {
          silence_s: Math.round(silenceS),
          content: finalContent,
          sent,
          anchor: lastTranscript
            ? {
                transcript_id: lastTranscript.transcript_id,
                speaker_id: lastTranscript.user_id ?? '',
                speaker_name: lastTranscript.speaker_name ?? '',
                text: lastTranscript.text?.trim() ?? '',
              }
            : null,
        },
        window_start: windowStart,
      }).catch((err) => {
        logger.error('writeDiscussionState(group_silence) failed', {
          sessionId: this.sessionId,
          message: (err as Error).message,
        });
      });
    } catch (err) {
      logger.error('checkGroupSilence failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }

  // ── 成员分析链：默认每 60s 触发一次；指标与行动层上下文均使用 120s 窗口 ─────────────

  private async runAnalysisPipeline(scheduledFor: Date): Promise<void> {
    try {
      const members = await getSessionMembers(this.sessionId);
      const memberIds = members.map((m) => m.user_id);
      if (memberIds.length === 0) return;

      const windowEnd = scheduledFor;
      // 触发频率仍为 60s；判断依据统一使用 120s 窗口，会话前两分钟内用 sessionStartedAt 兜底
      const longWindowStart = new Date(
        Math.max(this.sessionStartedAt.getTime(), windowEnd.getTime() - config.agent.longIntervalMs),
      );

      const startedAt = Date.now();
      const runId = buildRunId('reasoning', this.sessionId, longWindowStart);
      logger.info('===== reasoning run begin =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        metrics_window_start: longWindowStart.toISOString(),
        context_window_start: longWindowStart.toISOString(),
        window_end: windowEnd.toISOString(),
      });

      // Step1：感知层（含论证结构批量判定，120s 窗口，同步 await）
      const perceptionResult = await runPerceptionPipeline({
        sessionId: this.sessionId,
        memberIds,
        windowStart: longWindowStart,
        windowEnd,
      });

      if (!perceptionResult) return;

      // Step2：读当前摘要与本轮发言（组级窗口 120s）
      const [summaryRow, transcripts] = await Promise.all([
        getLastSummary(this.sessionId),
        getTranscriptsInWindowPreferCache(
          this.sessionId,
          longWindowStart,
          windowEnd,
        ),
      ]);
      const summaryText = summaryRow?.content ?? '';

      // Step3：行动层（heavy_model 单次大 JSON 调用，组级窗口 120s）
      void runActionLayer({
        sessionId: this.sessionId,
        perceptionResult,
        windowStart: longWindowStart,
        memberIds,
        summaryText,
        transcripts,
        onGroupSilenceNotified: () => this.markGroupSilenceTriggered(Date.now()),
        onPushQueued: () => this.triggerPushDispatcher('queued'),
      }).catch((err) => {
        logger.error('action failed', {
          sessionId: this.sessionId,
          message: (err as Error).message,
        });
      });

      logger.info('===== reasoning run end =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        duration_ms: Date.now() - startedAt,
      });
    } catch (err) {
      logger.error('runAnalysisPipeline failed', {
        sessionId: this.sessionId,
        message: (err as Error).message,
      });
    }
  }

  // ── 信息缺口链：每 60s 召回候选词；每 120s 基于最近两轮候选词决定是否推按钮 ───────

  private async runInfoGapPipeline(scheduledFor: Date): Promise<void> {
    try {
      const members = await getSessionMembers(this.sessionId);
      const memberIds = members.map((m) => m.user_id);
      if (memberIds.length < 2) return;

      const windowEnd = scheduledFor;
      const recallWindowStart = new Date(
        Math.max(this.sessionStartedAt.getTime(), windowEnd.getTime() - config.agent.infoGapIntervalMs),
      );
      const decisionWindowStart = new Date(
        Math.max(this.sessionStartedAt.getTime(), windowEnd.getTime() - config.agent.infoGapDecisionIntervalMs),
      );

      const recall = await recallInfoGapKeywords(
        this.sessionId,
        recallWindowStart,
        windowEnd,
        memberIds,
      );
      this.infoGapCandidates.push(...recall.candidates);
      this.trimInfoGapCandidates(decisionWindowStart);

      if (!this.isInfoGapDecisionPoint(scheduledFor)) {
        logger.info('info_gap 关键词召回完成，未到按钮决策点', {
          sessionId: this.sessionId,
          scheduled_for: scheduledFor.toISOString(),
          candidates: recall.candidates.length,
        });
        return;
      }

      const candidatesForDecision = this.infoGapCandidates.filter(
        (item) => item.windowEnd > decisionWindowStart && item.windowEnd <= windowEnd,
      );
      logger.info('info_gap 按钮决策开始', {
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        window_start: decisionWindowStart.toISOString(),
        candidates: candidatesForDecision.length,
      });

      await decideInfoGapButtons({
        sessionId: this.sessionId,
        windowStart: decisionWindowStart,
        memberIds,
        candidates: candidatesForDecision,
      });
    } catch (err) {
      logger.error('runInfoGapPipeline failed', {
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
      await runSummary(this.sessionId, windowStart, windowEnd);
      logger.info('===== summary run end =====', {
        run_id: runId,
        sessionId: this.sessionId,
        scheduled_for: scheduledFor.toISOString(),
        duration_ms: Date.now() - startedAt,
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

  private isInfoGapDecisionPoint(scheduledFor: Date): boolean {
    const elapsedMs = scheduledFor.getTime() - this.sessionStartedAt.getTime();
    return elapsedMs > 0 && elapsedMs % config.agent.infoGapDecisionIntervalMs === 0;
  }

  private trimInfoGapCandidates(windowStart: Date): void {
    this.infoGapCandidates = this.infoGapCandidates.filter((item) => item.windowEnd > windowStart);
  }
}
