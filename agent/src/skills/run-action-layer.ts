import { createLogger } from '../logger';
import { config } from '../config';
import {
  writePushQueueItem,
  writeDiscussionState,
  writeInfoGapButton,
  dismissPendingInfoGapButtonsBeforeWindow,
  hasPendingInfoGapKeyword,
  hasClickedInfoGapKeywordInRecentWindows,
  getPendingInfoGapButtonCount,
} from '../db/queries';
import {
  assessGap,
  embed,
  notifyGroupSilence,
  notifyInfoGapButton,
} from '../http/nlp-client';
import type { Trigger } from './run-reasoning-layer';
import type { Transcript } from '../db/queries';
import {
  generatePushContent,
  validateStructuredAnchor,
  type StructuredAnchor,
} from './generate-push-content';

const logger = createLogger('action-layer');
const GROUP_SILENCE_FIXED_CONTENT = '小组已沉默超过30秒，大家可以继续讨论～';
const INFO_GAP_CONFIDENCE_THRESHOLD = 0.7;
const INFO_GAP_MAX_PENDING = 3;
const INFO_GAP_RECENT_CLICKED_WINDOWS = 3;

type DirectPushTriggerType = 'low_participation' | 'shallow_discussion';
type DirectPushTrigger = Trigger & {
  type: DirectPushTriggerType;
  userId: string;
};

const PRIORITY: Record<string, number> = {
  group_silence: 1,
  low_participation: 2,
  shallow_discussion: 3,
  info_gap: 99,
};

interface SelectedTarget {
  trigger: DirectPushTrigger;
  recipientUserIds: string[];
}

function isDirectPushTrigger(trigger: Trigger): trigger is DirectPushTrigger {
  return (
    (trigger.type === 'low_participation' || trigger.type === 'shallow_discussion')
    && typeof trigger.userId === 'string'
    && trigger.userId.trim().length > 0
  );
}

function toGeneratedItemKey(triggerType: Trigger['type'], targetUserId: string): string {
  return `${triggerType}:${targetUserId}`;
}

export async function runActionLayer(params: {
  sessionId: string;
  triggers: Trigger[];
  windowStart: Date;
  memberIds: string[];
  summaryText: string;
  transcripts: Transcript[];
  onGroupSilenceNotified?: () => void;
}): Promise<void> {
  const { sessionId, triggers, windowStart, memberIds, summaryText, transcripts, onGroupSilenceNotified } = params;

  if (triggers.length === 0) {
    logger.info('行动层：无触发，跳过', { sessionId });
    return;
  }

  const infoGapTriggers = triggers.filter((t) => t.type === 'info_gap');
  if (infoGapTriggers.length > 0) {
    try {
      const dismissed = await dismissPendingInfoGapButtonsBeforeWindow(sessionId, windowStart);
      if (dismissed > 0) {
        logger.info(`[信息缺口] 已将历史 pending 按钮标记为 dismissed，数量=${dismissed}`, { sessionId });
      }
    } catch (err) {
      logger.warn('[信息缺口] 按钮过期处理失败，继续后续流程', { sessionId, message: (err as Error).message });
    }

    const keywordToScore = new Map<string, number>();
    for (const trigger of infoGapTriggers) {
      if (!trigger.keyword) continue;
      const current = keywordToScore.get(trigger.keyword);
      const score = trigger.skwScore ?? 0;
      keywordToScore.set(trigger.keyword, current === undefined ? score : Math.min(current, score));
    }
    const candidateKeywords = Array.from(keywordToScore.keys());

    if (candidateKeywords.length > 0) {
      const memberTexts = buildMemberTextsForAssess(memberIds, transcripts);
      const packed = packAssessContext(summaryText, memberTexts);
      const assessItems = await assessGap({
        keywords: candidateKeywords,
        summary: packed.summary,
        member_texts: packed.memberTexts,
        skw_scores: Object.fromEntries(keywordToScore.entries()),
      });

      const actionable = assessItems.filter((item) =>
        item.needs_prompt
        && item.confidence >= INFO_GAP_CONFIDENCE_THRESHOLD
        && item.target_user_id.trim().length > 0,
      );

      for (const item of actionable) {
        const uid = item.target_user_id.trim();
        if (!memberIds.includes(uid)) {
          logger.info(`[信息缺口] 目标用户不在会话内，跳过 user=${uid} keyword=${item.keyword}`, { sessionId });
          continue;
        }

        const keyword = item.keyword.trim();
        if (!keyword) continue;

        try {
          const sameKeywordPending = await hasPendingInfoGapKeyword(sessionId, uid, keyword);
          if (sameKeywordPending) {
            logger.info(`[信息缺口] 同词 pending 已存在，跳过 user=${uid} keyword=${keyword}`, { sessionId });
            continue;
          }

          const clickedRecently = await hasClickedInfoGapKeywordInRecentWindows(
            sessionId,
            uid,
            keyword,
            windowStart,
            INFO_GAP_RECENT_CLICKED_WINDOWS,
            config.agent.longIntervalMs,
          );
          if (clickedRecently) {
            logger.info(`[信息缺口] 最近窗口已点击过该词，跳过 user=${uid} keyword=${keyword}`, { sessionId });
            continue;
          }

          const pendingCount = await getPendingInfoGapButtonCount(sessionId, uid);
          if (pendingCount >= INFO_GAP_MAX_PENDING) {
            logger.info(`[信息缺口] pending 数已达上限，跳过 user=${uid} pending=${pendingCount}`, { sessionId });
            continue;
          }

          const score = item.skw_score ?? keywordToScore.get(keyword) ?? 0;
          const buttonId = await writeInfoGapButton({
            session_id: sessionId,
            user_id: uid,
            keyword,
            skw_score: score,
            window_start: windowStart,
            gap_type: item.gap_type,
            confidence: item.confidence,
            llm_reason: item.reason,
          });
          if (!buttonId) {
            logger.info(`[信息缺口] 写按钮冲突或未插入 user=${uid} keyword=${keyword}`, { sessionId });
            continue;
          }

          logger.info(
            `[信息缺口] 写按钮成功 user=${uid} keyword=${keyword} confidence=${item.confidence.toFixed(2)} reason=${item.reason}`,
            { sessionId },
          );

          await notifyInfoGapButton({
            session_id: sessionId,
            user_id: uid,
            button_id: buttonId,
            keyword,
            skw_score: score,
            window_start: windowStart.toISOString(),
          });
        } catch (err) {
          logger.error(`[信息缺口] 按钮写入/通知失败 user=${uid} keyword=${keyword}`, {
            sessionId,
            message: (err as Error).message,
          });
        }
      }
    }
  }

  const groupSilenceTriggers = triggers.filter((t) => t.type === 'group_silence');
  if (groupSilenceTriggers.length > 0) {
    const sent = await notifyGroupSilence(sessionId, GROUP_SILENCE_FIXED_CONTENT);
    if (sent) {
      logger.info('group_silence 直接广播成功', { sessionId });
      onGroupSilenceNotified?.();
    } else {
      logger.warn('group_silence 广播失败', { sessionId });
    }
    logger.info('group_silence 触发时按优先级跳过其余个人推送', { sessionId });
    return;
  }

  const mainTriggers = triggers
    .filter(isDirectPushTrigger)
    .sort((a, b) => (PRIORITY[a.type] ?? 99) - (PRIORITY[b.type] ?? 99));

  const selectedTargets: SelectedTarget[] = [];
  const reservedUsers = new Set<string>();

  for (const trigger of mainTriggers) {
    for (const uid of trigger.targetUsers) {
      if (reservedUsers.has(uid)) continue;

      reservedUsers.add(uid);
      selectedTargets.push({
        trigger,
        recipientUserIds: [uid],
      });
    }
  }

  if (selectedTargets.length === 0) {
    logger.info('行动层：无可用个人触发，跳过内容生成', { sessionId });
    return;
  }

  const generatedItems = await generatePushContent({
    sessionId,
    triggers: selectedTargets.map((item) => item.trigger),
    transcripts,
    summaryText,
    memberIds,
  });

  logger.info(`新 skill 返回成员分析数量=${generatedItems.length}`, { sessionId });

  const selectedTargetMap = new Map<string, SelectedTarget>(
    selectedTargets.map((item) => [toGeneratedItemKey(item.trigger.type, item.trigger.userId ?? ''), item]),
  );

  let persistedCount = 0;
  for (const item of generatedItems) {
    const selected = selectedTargetMap.get(toGeneratedItemKey(item.triggerType, item.targetUserId));
    if (!selected) {
      logger.warn(`新 skill 返回了未知目标 type=${item.triggerType} user=${item.targetUserId}`, { sessionId });
      continue;
    }

    if (!item.needsPrompt || !item.content.trim()) {
      continue;
    }

    const anchor = validateStructuredAnchor({
      anchor: item.anchor,
      transcripts,
      memberIds,
    });
    if (!anchor) {
      logger.warn(`anchor 校验失败，丢弃推送 type=${item.triggerType} user=${item.targetUserId}`, { sessionId });
      continue;
    }

    for (const recipientUserId of selected.recipientUserIds) {
      const persisted = await persistPushDecision({
        sessionId,
        trigger: selected.trigger,
        targetUserId: recipientUserId,
        content: item.content.trim(),
        anchor,
        windowStart,
      });
      if (persisted) {
        persistedCount += 1;
      }
    }
  }

  logger.info(`最终真正落库推送的数量=${persistedCount}`, { sessionId });
}

function approxTokenCount(text: string): number {
  const cjkEstimate = Math.ceil(text.length / 2);
  const latinEstimate = text.split(/\s+/).filter(Boolean).length;
  return Math.max(cjkEstimate, latinEstimate);
}

function buildMemberTextsForAssess(
  memberIds: string[],
  transcripts: Transcript[],
): Record<string, string[]> {
  const linesByUser: Record<string, string[]> = {};
  for (const uid of memberIds) linesByUser[uid] = [];

  for (const t of transcripts) {
    if (!t.user_id || !(t.user_id in linesByUser)) continue;
    const line = (t.text ?? '').trim();
    if (!line) continue;
    linesByUser[t.user_id].push(line);
  }

  return linesByUser;
}

function packAssessContext(
  summaryText: string,
  linesByUser: Record<string, string[]>,
): { summary: string; memberTexts: Record<string, string> } {
  const summary = summaryText.slice(0, 500);
  const buildWithPerUserLimit = (limit: number): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const [uid, lines] of Object.entries(linesByUser)) {
      const selected = lines.slice(-limit);
      out[uid] = selected.join('\n');
    }
    return out;
  };

  let memberTexts = buildWithPerUserLimit(20);
  let totalTokens = approxTokenCount(summary);
  for (const text of Object.values(memberTexts)) {
    totalTokens += approxTokenCount(text);
  }

  if (totalTokens > 3000) {
    memberTexts = buildWithPerUserLimit(10);
  }

  return { summary, memberTexts };
}

async function persistPushDecision(params: {
  sessionId: string;
  trigger: DirectPushTrigger;
  targetUserId: string;
  content: string;
  anchor: StructuredAnchor;
  windowStart: Date;
}): Promise<boolean> {
  const { sessionId, trigger, targetUserId, content, anchor, windowStart } = params;

  try {
    const embeddings = await embed([content]);
    const contentEmbedding = embeddings[0];

    if (!contentEmbedding || contentEmbedding.length === 0) {
      logger.warn('push embedding 为空，跳过入队', { sessionId, targetUserId });
      return false;
    }

    const queueId = await writePushQueueItem({
      session_id: sessionId,
      target_user_id: targetUserId,
      state_type: trigger.type,
      push_content: content,
      content_embedding: contentEmbedding,
      analysis_window_start: windowStart,
    });

    await writeDiscussionState({
      session_id: sessionId,
      state_type: trigger.type,
      target_user_id: targetUserId,
      trigger_metrics: {
        ...trigger.triggerMetrics,
        queued_push_id: queueId,
        anchor: {
          transcript_id: anchor.transcriptId,
          speaker_id: anchor.speakerId,
          text: anchor.text,
        },
      },
      window_start: windowStart,
    });
  } catch (err) {
    logger.error('persistPushDecision 失败', { sessionId, message: (err as Error).message });
    return false;
  }

  logger.info(`推送已入队 用户=${targetUserId} state=${trigger.type} 文案="${content}"`, { sessionId });
  return true;
}
