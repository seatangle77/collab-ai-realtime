import { createLogger } from '../logger';
import {
  writePushQueueItem,
  writeDiscussionState,
  dismissPendingInfoGapButtonsBeforeWindow,
} from '../db/queries';
import {
  embed,
  notifyGroupSilence,
} from '../http/nlp-client';
import type { Trigger } from './run-reasoning-layer';
import type { Transcript } from '../db/queries';
import {
  generatePushContent,
  validateStructuredAnchor,
  type StructuredAnchor,
} from './generate-push-content';

const logger = createLogger('action-layer');

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

  }

  const groupSilenceTriggers = triggers.filter((t) => t.type === 'group_silence');
  if (groupSilenceTriggers.length > 0) {
    const generatedItems = await generatePushContent({
      sessionId,
      triggers: groupSilenceTriggers,
      transcripts,
      summaryText,
      memberIds,
    });
    const silenceItem = generatedItems.find((item) => item.triggerType === 'group_silence');
    const content = silenceItem?.content?.trim() || '先聊聊你们各自最关心的是哪个方面？';
    const sent = await notifyGroupSilence(sessionId, content);
    if (sent) {
      logger.info(`group_silence 广播成功，内容="${content}"`, { sessionId });
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
