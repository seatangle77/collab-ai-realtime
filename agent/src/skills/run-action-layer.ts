import { createLogger } from '../logger';
import {
  writePushQueueItem,
  writeInfoGapButton,
} from '../db/queries';
import {
  generatePushBatchAnalysis,
  embed,
  notifyGroupSilence,
  notifyInfoGapButton,
} from '../http/nlp-client';
import type {
  BatchTargetInput,
  ChallengeType,
} from '../http/nlp-client';
import type { Trigger } from './run-reasoning-layer';
import type { Transcript } from '../db/queries';

const logger = createLogger('action-layer');
const AI_TARGET_USER_ALL = 'ALL';
const GROUP_SILENCE_FIXED_CONTENT = '小组已沉默超过30秒，大家可以继续讨论～';

type BatchSupportedTrigger = Exclude<Trigger['type'], 'info_gap'>;

function isBatchSupportedTrigger(
  trigger: Trigger,
): trigger is Trigger & { type: BatchSupportedTrigger } {
  return trigger.type !== 'info_gap';
}

// ── 优先级（数字越小越优先） ───────────────────────────────────────────────────

const PRIORITY: Record<string, number> = {
  group_silence:     1,
  low_participation: 2,
  shallow_discussion: 3,
  info_gap:          99, // 不参与排序，单独处理
};

interface PreparedBatchTarget {
  target: BatchTargetInput;
  triggerType: Trigger['type'];
  recipientUserIds: string[];
  metrics: Record<string, unknown>;
}

interface SelectedTarget {
  trigger: Trigger & { type: BatchSupportedTrigger };
  aiTargetUserId: string;
  recipientUserIds: string[];
}

// ── 主函数 ────────────────────────────────────────────────────────────────────

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

  // 格式化发言文本，供 Prompt 使用
  const transcriptText = transcripts
    .map((t) => `${t.user_id ?? '未知'}：${t.text ?? ''}`)
    .filter((line) => line.trim())
    .join('\n');

  // ── 处理信息缺口（不走冷却，直接写按钮）────────────────────────────────────
  const infoGapTriggers = triggers.filter((t) => t.type === 'info_gap');
  for (const trigger of infoGapTriggers) {
    for (const uid of trigger.targetUsers) {
      let buttonId: string | null = null;
      try {
        buttonId = await writeInfoGapButton({
          session_id: sessionId,
          user_id: uid,
          keyword: trigger.keyword!,
          skw_score: trigger.skwScore!,
          window_start: windowStart,
        });
        if (buttonId) {
          logger.info(`[信息缺口] 写按钮 用户=${uid} 关键词=${trigger.keyword} id=${buttonId}`, { sessionId });
        } else {
          logger.info(`[信息缺口] 按钮已存在，跳过 用户=${uid} 关键词=${trigger.keyword}`, { sessionId });
        }
      } catch (err) {
        logger.error(`[信息缺口] 写按钮失败 用户=${uid}`, { sessionId, message: (err as Error).message });
        continue;
      }

      // 写库成功后，通知前端通过 WebSocket 刷新按钮
      if (buttonId) {
        try {
          await notifyInfoGapButton({
            session_id: sessionId,
            user_id: uid,
            button_id: buttonId,
            keyword: trigger.keyword!,
            skw_score: trigger.skwScore!,
            window_start: windowStart.toISOString(),
          });
        } catch (err) {
          logger.warn(`[信息缺口] WS 通知失败 用户=${uid}`, { sessionId, message: (err as Error).message });
        }
      }
    }
  }

  // ── 处理其余3种触发（走冷却和优先级）───────────────────────────────────────
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

  // ── 处理其余2种触发（走冷却和优先级）───────────────────────────────────────
  const mainTriggers = triggers
    .filter(isBatchSupportedTrigger)
    .sort((a, b) => (PRIORITY[a.type] ?? 99) - (PRIORITY[b.type] ?? 99));

  const selectedTargets: SelectedTarget[] = [];
  const reservedUsers = new Set<string>();

  for (const trigger of mainTriggers) {
    if (trigger.type === 'group_silence') {
      const recipientUserIds: string[] = [];

      for (const uid of trigger.targetUsers) {
        if (reservedUsers.has(uid)) continue;

        recipientUserIds.push(uid);
      }

      if (recipientUserIds.length === 0) {
        continue;
      }

      recipientUserIds.forEach((uid) => reservedUsers.add(uid));
      selectedTargets.push({
        trigger,
        aiTargetUserId: AI_TARGET_USER_ALL,
        recipientUserIds,
      });
      continue;
    }

    for (const uid of trigger.targetUsers) {
      if (reservedUsers.has(uid)) continue;

      reservedUsers.add(uid);
      selectedTargets.push({
        trigger,
        aiTargetUserId: uid,
        recipientUserIds: [uid],
      });
    }
  }

  const batchTargets = buildBatchTargetsForAI(selectedTargets, transcripts);

  logger.info(`进入 batch AI 的目标数量=${batchTargets.length}`, { sessionId });

  if (batchTargets.length === 0) {
    logger.info('行动层：无可用目标，跳过 batch AI', { sessionId });
    return;
  }

  const items = await generatePushBatchAnalysis({
    session_id: sessionId,
    summary: summaryText,
    transcripts: transcriptText,
    members: memberIds.map((user_id) => ({ user_id })),
    targets: batchTargets.map(({ target }) => target),
  });

  logger.info(`batch AI 返回成员分析数量=${items.length}`, { sessionId });

  const actionableItems = items.filter((item) => item.needs_prompt && item.content.trim());
  logger.info(`batch AI needs_prompt=true 数量=${actionableItems.length}`, { sessionId });

  const targetMap = new Map<string, PreparedBatchTarget>(
    batchTargets.map((entry) => [toBatchTargetKey(entry.target.user_id, entry.target.challenge_type), entry]),
  );

  let persistedCount = 0;
  for (const item of actionableItems) {
    const prepared = targetMap.get(toBatchTargetKey(item.user_id, item.challenge_type));
    if (!prepared) {
      logger.warn(`batch AI 返回了未知目标 user=${item.user_id} challenge=${item.challenge_type}`, { sessionId });
      continue;
    }

    for (const recipientUserId of prepared.recipientUserIds) {
      const persisted = await persistPushDecision({
        sessionId,
        triggerType: prepared.triggerType,
        targetUserId: recipientUserId,
        content: item.content.trim(),
        windowStart,
      });
      if (persisted) {
        persistedCount += 1;
      }
    }
  }

  logger.info(`最终真正落库推送的数量=${persistedCount}`, { sessionId });
}

function buildBatchTargetsForAI(
  candidates: SelectedTarget[],
  transcripts: Transcript[],
): PreparedBatchTarget[] {
  return candidates.map(({ trigger, aiTargetUserId, recipientUserIds }) => {
    const metrics = trigger.triggerMetrics;
    const challengeType = toChallengeType(trigger.type);

    return {
      target: {
        user_id: aiTargetUserId,
        challenge_type: challengeType,
        evidence: buildEvidence(trigger, metrics, transcripts),
        diagnosis: buildDiagnosis(trigger.type, metrics),
        design_goal: buildDesignGoal(challengeType),
      },
      triggerType: trigger.type,
      recipientUserIds,
      metrics,
    };
  });
}

function toChallengeType(triggerType: BatchSupportedTrigger): ChallengeType {
  switch (triggerType) {
    case 'group_silence':
      return 'group_stagnation';
    case 'low_participation':
      return 'personal_stagnation';
    case 'shallow_discussion':
      return 'shallow_expression';
    default:
      throw new Error(`unsupported trigger type for batch target: ${triggerType}`);
  }
}

function buildEvidence(
  trigger: Trigger & { type: BatchSupportedTrigger },
  metrics: Record<string, unknown>,
  transcripts: Transcript[],
): Record<string, unknown> {
  switch (trigger.type) {
    case 'group_silence':
      return {
        silence_s: (metrics.silence_s as number) ?? 0,
      };
    case 'low_participation':
      return {
        speaking_ratio: (metrics.speaking_ratio as number) ?? 0,
      };
    case 'shallow_discussion':
      return {
        ...sanitizeEvidence(metrics),
        member_quotes: collectMemberQuotes(trigger.userId, transcripts),
      };
    default:
      throw new Error(`unsupported trigger type for evidence: ${trigger.type}`);
  }
}

function collectMemberQuotes(userId: string | undefined, transcripts: Transcript[]): string {
  if (!userId) return '';

  return transcripts
    .filter((item) => item.user_id === userId && item.text?.trim())
    .map((item) => `${item.user_id ?? '未知'}：${item.text?.trim() ?? ''}`)
    .join('\n');
}

function buildDiagnosis(
  triggerType: BatchSupportedTrigger,
  metrics: Record<string, unknown>,
): string {
  switch (triggerType) {
    case 'group_silence':
      return `全组讨论已持续沉默${(metrics.silence_s as number) ?? 0}秒，陷入僵局`;
    case 'low_participation':
      return `该成员过去120秒发言占比为${Math.round((((metrics.speaking_ratio as number) ?? 0) * 100) * 10) / 10}%，可能陷入思路停滞`;
    case 'shallow_discussion':
      return '该成员发言重复且缺乏论证，停留在表面表达';
    default:
      throw new Error(`unsupported trigger type for diagnosis: ${triggerType}`);
  }
}

function buildDesignGoal(challengeType: ChallengeType): string {
  switch (challengeType) {
    case 'group_stagnation':
      return '提供一个尚未覆盖的新讨论角度，帮助全组重启讨论';
    case 'personal_stagnation':
      return '提供一个该成员尚未提及的新观点，帮助其重新进入讨论';
    case 'shallow_expression':
      return '提供一个追问，促使其补充理由、依据或例子';
    case 'information_gap':
      return '提供一句简洁定义或相关论据，帮助其修正理解偏差';
    case 'none':
      return '无需干预';
    default:
      throw new Error(`unsupported challenge type for design goal: ${challengeType}`);
  }
}

function sanitizeEvidence(metrics: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(metrics).filter(([, value]) => value !== undefined),
  );
}

function toBatchTargetKey(userId: string, challengeType: ChallengeType): string {
  return `${userId}:${challengeType}`;
}

// ── 推送持久化 ────────────────────────────────────────────────────────────────

async function persistPushDecision(params: {
  sessionId: string;
  triggerType: Trigger['type'];
  targetUserId: string;
  content: string;
  windowStart: Date;
}): Promise<boolean> {
  const { sessionId, triggerType, targetUserId, content, windowStart } = params;

  try {
    const embeddings = await embed([content]);
    const contentEmbedding = embeddings[0];

    if (!contentEmbedding || contentEmbedding.length === 0) {
      logger.warn('push embedding 为空，跳过入队', { sessionId, targetUserId });
      return false;
    }

    await writePushQueueItem({
      session_id: sessionId,
      target_user_id: targetUserId,
      state_type: triggerType,
      push_content: content,
      content_embedding: contentEmbedding,
      analysis_window_start: windowStart,
    });
  } catch (err) {
    logger.error('writePushQueueItem 失败', { sessionId, message: (err as Error).message });
    return false;
  }

  logger.info(`推送已入队 用户=${targetUserId} state=${triggerType} 文案="${content}"`, { sessionId });
  return true;
}
