import { createLogger } from '../logger';
import { nanoid } from 'nanoid';
import {
  writePushQueueItem,
  writeDiscussionState,
  writeAiPushAnalysis,
  trimPendingMemberInterventionQueue,
} from '../db/queries';
import { embed, analyzeMembers } from '../http/nlp-client';
import type { PipelineResult } from './run-perception-pipeline';
import type { Transcript } from '../db/queries';

const logger = createLogger('action-layer');

// ── anchor 校验 ────────────────────────────────────────────────────────────────

interface NormalizedAnchor {
  transcriptId: string;
  speakerId: string;
  speakerName: string;
  text: string;
}

function normalizeAnchorFromTranscript(
  anchor: { transcript_id: string; speaker_id?: string; speaker_name?: string; text: string } | null | undefined,
  transcripts: Transcript[],
  memberIds: string[],
): NormalizedAnchor | null {
  if (!anchor) return null;
  const t = transcripts.find((item) => item.transcript_id === anchor.transcript_id);
  if (!t || !t.user_id) return null;
  if (!memberIds.includes(t.user_id)) return null;

  const orig = t.text?.trim() ?? '';
  const anchorText = anchor.text?.trim() ?? '';
  if (!orig || !anchorText) return null;
  if (!orig.includes(anchorText) && !anchorText.includes(orig)) return null;

  return {
    transcriptId: t.transcript_id,
    speakerId: t.user_id,
    speakerName: t.speaker_name?.trim() ?? '',
    text: anchorText,
  };
}

function validateAnchor(
  anchor: { transcript_id: string; speaker_id: string; speaker_name: string; text: string } | null | undefined,
  transcripts: Transcript[],
  memberIds: string[],
  targetUserId: string,
  challengeType: string,
): NormalizedAnchor | null {
  const normalized = normalizeAnchorFromTranscript(anchor, transcripts, memberIds);
  if (!normalized) return null;
  if (challengeType === 'shallow' && normalized.speakerId !== targetUserId) return null;
  return normalized;
}

function shouldAllowStagnationWithoutAnchor(params: {
  challengeType: string;
  speakingRatio: number;
  silenceS: number;
  userTranscriptCount: number;
}): boolean {
  if (params.challengeType !== 'stagnation') return false;
  return params.userTranscriptCount === 0 || params.speakingRatio < 0.15 || params.silenceS >= 30;
}

function toAnchorRecord(anchor: NormalizedAnchor): Record<string, string> {
  return {
    transcript_id: anchor.transcriptId,
    speaker_id: anchor.speakerId,
    speaker_name: anchor.speakerName,
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
  const memberInputById = new Map(memberInputs.map((member) => [member.user_id, member]));
  const transcriptCountByUserId = new Map<string, number>();
  for (const transcript of transcriptInputs) {
    transcriptCountByUserId.set(
      transcript.user_id,
      (transcriptCountByUserId.get(transcript.user_id) ?? 0) + 1,
    );
  }

  logger.info('行动层：调用 heavy_model 全员分析', { sessionId, member_count: memberIds.length });

  const analysisItems = await analyzeMembers({
    summary: summaryText,
    transcripts: transcriptInputs,
    members: memberInputs,
  });

  logger.info(`行动层：heavy_model 返回 ${analysisItems.length} 条分析`, { sessionId });

  let persistedCount = 0;
  const candidates: Array<{
    item: (typeof analysisItems)[number];
    content: string;
    anchor: NormalizedAnchor | null;
    baseRow: {
      id: string;
      session_id: string;
      target_user_id: string;
      state_type: string;
      window_start: Date;
      ai_needs_prompt: boolean;
      ai_anchor: Record<string, string> | null;
      ai_content: string | null;
      drop_reason: 'needs_prompt_false';
    };
  }> = [];

  for (const item of analysisItems) {
    const content = item.content.trim();
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

    if (!item.needs_prompt || !content) {
      void writeAiPushAnalysis({
        ...baseRow,
        ai_analysis: item.analysis ?? null,
        drop_reason: !item.needs_prompt ? 'needs_prompt_false' : 'content_empty',
      }).catch((err) => {
        logger.error('writeAiPushAnalysis(drop) failed', { sessionId, message: (err as Error).message });
      });
      continue;
    }

    const anchor = validateAnchor(
      item.anchor,
      transcripts,
      memberIds,
      item.user_id,
      item.challenge_type,
    );
    const memberMetrics = memberInputById.get(item.user_id);
    const allowWithoutAnchor = shouldAllowStagnationWithoutAnchor({
      challengeType: item.challenge_type,
      speakingRatio: memberMetrics?.speaking_ratio ?? 0,
      silenceS: memberMetrics?.silence_s ?? 0,
      userTranscriptCount: transcriptCountByUserId.get(item.user_id) ?? 0,
    });
    if (!anchor && !allowWithoutAnchor) {
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
    if (!anchor && allowWithoutAnchor) {
      logger.info(`stagnation 低参与/未发言，允许无 anchor 推送 user=${item.user_id}`, { sessionId });
    }

    candidates.push({ item, content, anchor, baseRow });
  }

  if (candidates.length === 0) {
    logger.info(`行动层完成，入队数量=${persistedCount}`, { sessionId });
    return;
  }

  let embeddings: number[][];
  try {
    embeddings = await embed(candidates.map((candidate) => candidate.content));
  } catch (err) {
    logger.error('batch embed failed, skip current action candidates', {
      sessionId,
      candidate_count: candidates.length,
      message: (err as Error).message,
    });
    logger.info(`行动层完成，入队数量=${persistedCount}`, { sessionId });
    return;
  }

  for (const [index, candidate] of candidates.entries()) {
    const { item, content, anchor, baseRow } = candidate;

    try {
      const contentEmbedding = embeddings[index];
      if (!contentEmbedding || contentEmbedding.length === 0) {
        logger.warn('push embedding 为空，跳过入队', { sessionId, targetUserId: item.user_id });
        continue;
      }

      const queueId = await writePushQueueItem({
        session_id: sessionId,
        target_user_id: item.user_id,
        state_type: item.challenge_type,
        push_content: content,
        content_embedding: contentEmbedding,
        analysis_window_start: windowStart,
      });

      if (item.challenge_type === 'stagnation' || item.challenge_type === 'shallow') {
        const skippedCount = await trimPendingMemberInterventionQueue({
          sessionId,
          targetUserId: item.user_id,
          keepLatest: 2,
        });
        if (skippedCount > 0) {
          logger.info(`成员干预队列已保留最新2条，跳过旧 pending 数量=${skippedCount} user=${item.user_id}`, { sessionId });
        }
      }

      await writeDiscussionState({
        session_id: sessionId,
        state_type: item.challenge_type,
        target_user_id: item.user_id,
        trigger_metrics: {
          challenge_type: item.challenge_type,
          analysis: item.analysis,
          queued_push_id: queueId,
          anchor: anchor ? toAnchorRecord(anchor) : null,
        },
        window_start: windowStart,
      });

      void writeAiPushAnalysis({
        ...baseRow,
        ai_needs_prompt: true,
        ai_anchor: anchor ? toAnchorRecord(anchor) : null,
        ai_content: content,
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
