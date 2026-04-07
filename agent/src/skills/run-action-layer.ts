import { createLogger } from '../logger';
import {
  writeDiscussionState,
  writePushLog,
  writeInfoGapButton,
  getLastPushTimeForUser,
  getStateCooldownUntil,
} from '../db/queries';
import { generatePush, notifyPush } from '../http/nlp-client';
import type { Trigger } from './run-reasoning-layer';
import type { Transcript } from '../db/queries';

const logger = createLogger('action-layer');

// ── 冷却时间常量 ──────────────────────────────────────────────────────────────

const COOLDOWN_SAME_STATE_MS  = 240_000;  // 同状态 240s
const COOLDOWN_CROSS_STATE_MS = 120_000;  // 同用户跨状态 120s

// ── 优先级（数字越小越优先） ───────────────────────────────────────────────────

const PRIORITY: Record<string, number> = {
  group_silence:     1,
  low_participation: 2,
  shallow_discussion: 3,
  info_gap:          99, // 不参与排序，单独处理
};

// ── 主函数 ────────────────────────────────────────────────────────────────────

export async function runActionLayer(params: {
  sessionId: string;
  triggers: Trigger[];
  windowStart: Date;
  memberIds: string[];
  summaryText: string;
  transcripts: Transcript[];
}): Promise<void> {
  const { sessionId, triggers, windowStart, memberIds, summaryText, transcripts } = params;

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
      try {
        await writeInfoGapButton({
          session_id: sessionId,
          user_id: uid,
          keyword: trigger.keyword!,
          skw_score: trigger.skwScore!,
          window_start: windowStart,
        });
        logger.info(`[信息缺口] 写按钮 用户=${uid} 关键词=${trigger.keyword}`, { sessionId });
      } catch (err) {
        logger.error(`[信息缺口] 写按钮失败 用户=${uid}`, { sessionId, message: (err as Error).message });
      }
    }
  }

  // ── 处理其余3种触发（走冷却和优先级）───────────────────────────────────────
  const mainTriggers = triggers
    .filter((t) => t.type !== 'info_gap')
    .sort((a, b) => (PRIORITY[a.type] ?? 99) - (PRIORITY[b.type] ?? 99));

  for (const trigger of mainTriggers) {
    for (const uid of trigger.targetUsers) {
      const passed = await checkCooldown(sessionId, trigger.type, uid);
      if (!passed) continue;

      await dispatchPush({
        sessionId,
        trigger,
        targetUserId: uid,
        windowStart,
        summaryText,
        transcriptText,
        memberIds,
      });
    }
  }
}

// ── 冷却检查 ──────────────────────────────────────────────────────────────────

async function checkCooldown(
  sessionId: string,
  stateType: string,
  userId: string,
): Promise<boolean> {
  const now = Date.now();

  // 单状态冷却：同一 state_type 对该用户的冷却截止时间
  try {
    const cooldownUntil = await getStateCooldownUntil(sessionId, stateType, userId);
    if (cooldownUntil && cooldownUntil.getTime() > now) {
      logger.info(`冷却中跳过 用户=${userId} state=${stateType} 剩余${Math.round((cooldownUntil.getTime() - now) / 1000)}s`, { sessionId });
      return false;
    }
  } catch (err) {
    logger.error('getStateCooldownUntil 失败', { sessionId, message: (err as Error).message });
  }

  // 跨状态冷却：该用户任意推送后 120s 内不再推
  try {
    const lastPush = await getLastPushTimeForUser(sessionId, userId);
    if (lastPush && now - lastPush.getTime() < COOLDOWN_CROSS_STATE_MS) {
      logger.info(`跨状态冷却 用户=${userId} 距上次推送${Math.round((now - lastPush.getTime()) / 1000)}s`, { sessionId });
      return false;
    }
  } catch (err) {
    logger.error('getLastPushTimeForUser 失败', { sessionId, message: (err as Error).message });
  }

  return true;
}

// ── 推送分发 ──────────────────────────────────────────────────────────────────

async function dispatchPush(params: {
  sessionId: string;
  trigger: Trigger;
  targetUserId: string;
  windowStart: Date;
  summaryText: string;
  transcriptText: string;
  memberIds: string[];
}): Promise<void> {
  const { sessionId, trigger, targetUserId, windowStart, summaryText, transcriptText } = params;
  const metrics = trigger.triggerMetrics;

  // 生成文案
  const content = await generatePush({
    trigger_type: trigger.type,
    summary: summaryText,
    transcripts: transcriptText,
    username: trigger.userId ?? '',
    silence_s: (metrics.silence_s as number) ?? 0,
    speaking_ratio: (metrics.speaking_ratio as number) ?? 0,
    triggered_metrics: (metrics.description as string) ?? '',
  });

  if (!content) {
    logger.error(`Qwen 生成文案为空，跳过推送 用户=${targetUserId} state=${trigger.type}`, { sessionId });
    return;
  }

  // 写 discussion_states
  const cooldownUntil = new Date(Date.now() + COOLDOWN_SAME_STATE_MS);
  let stateId: string;
  try {
    stateId = await writeDiscussionState({
      session_id: sessionId,
      state_type: trigger.type,
      target_user_id: trigger.type === 'group_silence' ? undefined : targetUserId,
      trigger_metrics: metrics,
      window_start: windowStart,
      push_cooldown_until: cooldownUntil,
    });
  } catch (err) {
    logger.error('writeDiscussionState 失败', { sessionId, message: (err as Error).message });
    return;
  }

  // 写 push_logs（glasses 渠道，由 agent 直接写库）
  try {
    await writePushLog({
      session_id: sessionId,
      state_id: stateId,
      target_user_id: targetUserId,
      push_content: content,
      push_channel: 'glasses',
    });
  } catch (err) {
    logger.error('writePushLog 失败', { sessionId, message: (err as Error).message });
  }

  // Web 渠道：通知后端写库并定向 WebSocket 推送
  await notifyPush(sessionId, targetUserId, content, stateId, trigger.type);

  logger.info(`推送完成 用户=${targetUserId} state=${trigger.type} 文案="${content}"`, { sessionId });
}
