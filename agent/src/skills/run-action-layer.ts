import { createLogger } from '../logger';
import { nanoid } from 'nanoid';
import {
  writePushQueueItem,
  writeDiscussionState,
  writeAiPushAnalysis,
  dismissPendingInfoGapButtonsBeforeWindow,
} from '../db/queries';
import { embed, analyzeMembers } from '../http/nlp-client';
import type { PipelineResult } from './run-perception-pipeline';
import type { Transcript } from '../db/queries';

const logger = createLogger('action-layer');

// ── anchor 校验 ────────────────────────────────────────────────────────────────

function validateAnchor(
  anchor: { transcript_id: string; speaker_id: string; speaker_name: string; text: string } | null | undefined,
  transcripts: Transcript[],
  memberIds: string[],
): { transcriptId: string; speakerId: string; speakerName: string; text: string } | null {
  if (!anchor) return null;
  const t = transcripts.find((item) => item.transcript_id === anchor.transcript_id);
  if (!t || !t.user_id) return null;
  if (!memberIds.includes(t.user_id)) return null;
  if (t.user_id !== anchor.speaker_id) return null;
  const name = t.speaker_name?.trim() ?? '';
  if (!name || name !== anchor.speaker_name) return null;
  const orig = t.text?.trim() ?? '';
  if (!orig) return null;
  if (!orig.includes(anchor.text) && !anchor.text.includes(orig)) return null;
  return {
    transcriptId: anchor.transcript_id,
    speakerId: t.user_id,
    speakerName: name,
    text: anchor.text,
  };
}

// ── 主函数 ────────────────────────────────────────────────────────────────────

export async function runActionLayer(params: {
  sessionId: string;
  perceptionResult: PipelineResult;
  windowStart: Date;
  memberIds: string[];
  summaryText: string;
  transcripts: Transcript[];
  onGroupSilenceNotified?: () => void;
}): Promise<void> {
  const { sessionId, perceptionResult, windowStart, memberIds, summaryText, transcripts } = params;

  if (memberIds.length === 0) {
    logger.info('行动层：成员列表为空，跳过', { sessionId });
    return;
  }

  // 过期历史 info_gap 按钮
  try {
    const dismissed = await dismissPendingInfoGapButtonsBeforeWindow(sessionId, windowStart);
    if (dismissed > 0) {
      logger.info(`[action] 已过期历史 info_gap 按钮 数量=${dismissed}`, { sessionId });
    }
  } catch (err) {
    logger.warn('[action] info_gap 按钮过期处理失败', { sessionId, message: (err as Error).message });
  }

  // 构造 transcripts 输入
  const transcriptInputs = transcripts
    .filter((t) => t.text?.trim() && t.user_id)
    .map((t) => ({
      transcript_id: t.transcript_id,
      user_id: t.user_id!,
      speaker_name: t.speaker_name?.trim() ?? '',
      text: t.text!.trim(),
    }));

  // 构造 members metrics 输入
  const memberInputs = memberIds.map((uid) => ({
    user_id: uid,
    speaking_ratio: perceptionResult.speakingRatios[uid] ?? 0,
    silence_s: perceptionResult.silenceSeconds[uid] ?? 0,
    ttr: perceptionResult.ttrs[uid] ?? null,
    arg_density: perceptionResult.argDensities[uid] ?? null,
    srep: perceptionResult.sreps[uid] ?? null,
    info_gain: perceptionResult.infoGains[uid] ?? null,
    reasoning_status: perceptionResult.hasReasoningMap[uid] ?? null,
    evidence_status: perceptionResult.hasEvidenceMap[uid] ?? null,
    reasoning_source: perceptionResult.reasoningSourceMap[uid] ?? null,
    evidence_source: perceptionResult.evidenceSourceMap[uid] ?? null,
  }));

  logger.info('行动层：调用 heavy_model 全员分析', { sessionId, member_count: memberIds.length });

  const analysisItems = await analyzeMembers({
    summary: summaryText,
    transcripts: transcriptInputs,
    members: memberInputs,
  });

  logger.info(`行动层：heavy_model 返回 ${analysisItems.length} 条分析`, { sessionId });

  let persistedCount = 0;

  for (const item of analysisItems) {
    const baseRow = {
      id: 'apa_' + nanoid(12),
      session_id: sessionId,
      target_user_id: item.user_id,
      state_type: item.challenge_type,
      window_start: windowStart,
      ai_needs_prompt: item.needs_prompt,
      ai_anchor: null as Record<string, string> | null,
      ai_content: item.content || null,
      drop_reason: 'needs_prompt_false' as const,
    };

    if (!item.needs_prompt || !item.content.trim()) {
      void writeAiPushAnalysis({
        ...baseRow,
        ai_analysis: item.analysis ?? null,
        drop_reason: !item.needs_prompt ? 'needs_prompt_false' : 'content_empty',
      }).catch((err) => {
        logger.error('writeAiPushAnalysis(drop) failed', { sessionId, message: (err as Error).message });
      });
      continue;
    }

    const anchor = validateAnchor(item.anchor, transcripts, memberIds);
    if (!anchor) {
      logger.warn(`anchor 校验失败，丢弃 type=${item.challenge_type} user=${item.user_id}`, { sessionId });
      void writeAiPushAnalysis({
        ...baseRow,
        ai_needs_prompt: true,
        ai_anchor: item.anchor as Record<string, string> | null,
        ai_analysis: item.analysis ?? null,
        drop_reason: 'anchor_invalid',
      }).catch((err) => {
        logger.error('writeAiPushAnalysis(anchor_invalid) failed', { sessionId, message: (err as Error).message });
      });
      continue;
    }

    try {
      const embeddings = await embed([item.content.trim()]);
      const contentEmbedding = embeddings[0];
      if (!contentEmbedding || contentEmbedding.length === 0) {
        logger.warn('push embedding 为空，跳过入队', { sessionId, targetUserId: item.user_id });
        continue;
      }

      const queueId = await writePushQueueItem({
        session_id: sessionId,
        target_user_id: item.user_id,
        state_type: item.challenge_type,
        push_content: item.content.trim(),
        content_embedding: contentEmbedding,
        analysis_window_start: windowStart,
      });

      await writeDiscussionState({
        session_id: sessionId,
        state_type: item.challenge_type,
        target_user_id: item.user_id,
        trigger_metrics: {
          challenge_type: item.challenge_type,
          analysis: item.analysis,
          queued_push_id: queueId,
          anchor: {
            transcript_id: anchor.transcriptId,
            speaker_id: anchor.speakerId,
            speaker_name: anchor.speakerName,
            text: anchor.text,
          },
        },
        window_start: windowStart,
      });

      void writeAiPushAnalysis({
        ...baseRow,
        ai_needs_prompt: true,
        ai_anchor: anchor as unknown as Record<string, string>,
        ai_content: item.content.trim(),
        ai_analysis: item.analysis ?? null,
        drop_reason: 'passed',
      }).catch((err) => {
        logger.error('writeAiPushAnalysis(passed) failed', { sessionId, message: (err as Error).message });
      });

      persistedCount += 1;
      logger.info(`推送已入队 user=${item.user_id} type=${item.challenge_type}`, { sessionId });
    } catch (err) {
      logger.error('persistPushDecision 失败', { sessionId, targetUserId: item.user_id, message: (err as Error).message });
    }
  }

  logger.info(`行动层完成，入队数量=${persistedCount}`, { sessionId });
}
