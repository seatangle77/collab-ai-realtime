import { createLogger } from '../logger';
import {
  claimPendingPushQueue,
  findDiscussionStateByQueuedPushId,
  getPendingPushQueue,
  recoverStaleProcessingItems,
  skipOtherPendingMemberInterventionQueueItems,
  updatePushQueueStatus,
  writeDiscussionState,
} from '../db/queries';
import { notifyPush } from '../http/nlp-client';
import { runPushFilterChain } from './push/run-push-filter-chain';
import { sameRoundDedupFilter } from './push/filters/same-round-dedup';
import { recentExactContentFilter } from './push/filters/recent-exact-content';
import { contentSimilarityFilter } from './push/filters/content-similarity';
import { vadCheckFilter } from './push/filters/vad-check';
import type { PushFilter } from './push/types';

const logger = createLogger('push-dispatcher');
const WS_TRACE = '[WS_TRACE]';

const PUSH_FILTERS: PushFilter[] = [
  sameRoundDedupFilter,    // 1. 同轮去重（纯内存，最快）
  recentExactContentFilter, // 2. 短时间完全相同文案去重（DB 查询）
  contentSimilarityFilter,  // 3. 内容相似度（DB 查询）
  vadCheckFilter,           // 4. VAD 说话检测（HTTP，最慢）
];

export const pushDispatcherHooks = {
  async shouldSkipPushQueueItem(): Promise<boolean> {
    return false;
  },
};

const PUSH_CLAIM_BATCH_SIZE = 20;
const PROCESSING_STALE_TIMEOUT_MS = 5 * 60 * 1000; // 5 分钟

export async function runPushDispatcher(sessionId: string): Promise<void> {
  logger.info('push dispatcher tick', { sessionId });

  const recovered = await recoverStaleProcessingItems(sessionId, PROCESSING_STALE_TIMEOUT_MS);
  if (recovered > 0) {
    logger.warn(`push dispatcher recovered stale processing items count=${recovered}`, { sessionId });
  }

  const pendingItems = await claimPendingPushQueue(sessionId, PUSH_CLAIM_BATCH_SIZE);
  const reservedUsers = new Set<string>();

  if (pendingItems.length === 0) {
    const pendingSnapshot = await getPendingPushQueue(sessionId);
    if (pendingSnapshot.length > 0) {
      logger.warn(`${WS_TRACE} push dispatcher claimed=0 but pending exists`, {
        sessionId,
        pending_count: pendingSnapshot.length,
        pending_items: pendingSnapshot.slice(0, 10).map((item) => ({
          id: item.id,
          target_user_id: item.target_user_id,
          state_type: item.state_type,
          analysis_window_start: item.analysis_window_start,
          created_at: item.created_at,
        })),
      });
    }
    logger.info('push dispatcher claimed=0', {
      sessionId,
      pending_count: pendingSnapshot.length,
      pending_items: pendingSnapshot.slice(0, 5).map((item) => ({
        id: item.id,
        target_user_id: item.target_user_id,
        state_type: item.state_type,
        analysis_window_start: item.analysis_window_start,
        created_at: item.created_at,
      })),
    });
    return;
  }

  logger.info(`push dispatcher claimed=${pendingItems.length}`, { sessionId });

  for (const item of pendingItems) {
    try {
      if (await pushDispatcherHooks.shouldSkipPushQueueItem()) {
        await updatePushQueueStatus(item.id, 'skipped', undefined, 'filter_hook');
        logger.info(`push skipped by hook queue_id=${item.id} user=${item.target_user_id}`, { sessionId });
        continue;
      }

      const outcome = await runPushFilterChain(
        { sessionId, item, reservedUsers },
        PUSH_FILTERS,
      );

      if (outcome.action === 'skip') {
        const skipReasonMap: Record<string, string> = {
          same_round_dedup: 'filter_same_round',
          recent_exact_content: 'filter_exact_content',
          content_similarity: 'filter_similar_content',
          hook_skip: 'filter_hook',
        };
        await updatePushQueueStatus(item.id, 'skipped', undefined, skipReasonMap[outcome.reasonCode] ?? outcome.reasonCode);
        logger.info(
          `push skipped queue_id=${item.id} user=${item.target_user_id} by=${outcome.by} reason=${outcome.reasonCode}`,
          { sessionId },
        );
        continue;
      }

      if (outcome.action === 'defer') {
        const deferReasonMap: Record<string, string> = {
          vad_speaking: 'filter_vad_speaking',
          hook_skip: 'filter_error',
        };
        await updatePushQueueStatus(item.id, 'deferred', undefined, deferReasonMap[outcome.reasonCode] ?? 'filter_error');
        logger.info(
          `push deferred queue_id=${item.id} user=${item.target_user_id} by=${outcome.by} reason=${outcome.reasonCode}`,
          { sessionId },
        );
        continue;
      }

      // outcome.action === 'proceed' → 执行推送
      const existingState = await findDiscussionStateByQueuedPushId({
        sessionId: item.session_id,
        queueId: item.id,
      });
      const stateId = existingState?.id ?? await writeDiscussionState({
        session_id: item.session_id,
        state_type: item.state_type,
        target_user_id: item.target_user_id,
        trigger_metrics: { queued_push_id: item.id },
        window_start: item.analysis_window_start,
      });

      const notifyResult = await notifyPush(
        item.session_id,
        item.target_user_id,
        item.push_content,
        stateId,
        item.state_type,
        item.id,
      );

      if (!notifyResult.ws_sent) {
        const retryable = notifyResult.delivery_reason === 'ws_user_not_connected'
          || notifyResult.delivery_reason === 'ws_send_error';
        if (notifyResult.delivery_reason === 'ws_user_not_connected') {
          logger.warn(
            `${WS_TRACE} push ws_user_not_connected queue_id=${item.id} user=${item.target_user_id}`,
            {
              sessionId,
              state_id: stateId,
              trigger_type: item.state_type,
              log_id: notifyResult.id,
            },
          );
        }
        await updatePushQueueStatus(item.id, retryable ? 'pending' : 'failed', undefined,
          retryable ? undefined : (notifyResult.delivery_reason ?? 'ws_failed'));
        logger.warn(
          `push not delivered queue_id=${item.id} user=${item.target_user_id} reason=${notifyResult.delivery_reason}`,
          {
            sessionId,
            delivery_status: notifyResult.delivery_status,
            retryable,
            log_id: notifyResult.id,
          },
        );
        continue;
      }

      const deliveredAt = new Date();
      reservedUsers.add(item.target_user_id);
      await updatePushQueueStatus(item.id, 'delivered', deliveredAt);
      if (item.state_type === 'stagnation' || item.state_type === 'shallow') {
        const skippedCount = await skipOtherPendingMemberInterventionQueueItems({
          sessionId: item.session_id,
          targetUserId: item.target_user_id,
          deliveredQueueId: item.id,
        });
        if (skippedCount > 0) {
          logger.info(`push delivered; skipped older member-intervention buffers count=${skippedCount} user=${item.target_user_id}`, { sessionId });
        }
      }
      logger.info(`push delivered queue_id=${item.id} user=${item.target_user_id}`, { sessionId });
    } catch (err) {
      logger.error(`push dispatch failed queue_id=${item.id}`, {
        sessionId,
        message: (err as Error).message,
      });
      await updatePushQueueStatus(item.id, 'failed', undefined, 'dispatch_exception');
    }
  }
}
