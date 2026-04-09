import { createLogger } from '../logger';
import {
  getPendingPushQueue,
  updatePushQueueStatus,
  writeDiscussionState,
  writePushLog,
} from '../db/queries';
import { notifyPush } from '../http/nlp-client';
import { runPushFilterChain } from './push/run-push-filter-chain';
import { sameRoundDedupFilter } from './push/filters/same-round-dedup';
import { contentSimilarityFilter } from './push/filters/content-similarity';
import { vadCheckFilter } from './push/filters/vad-check';
import type { PushFilter } from './push/types';

const logger = createLogger('push-dispatcher');

const PUSH_FILTERS: PushFilter[] = [
  sameRoundDedupFilter,    // 1. 同轮去重（纯内存，最快）
  contentSimilarityFilter, // 2. 内容相似度（DB 查询）
  vadCheckFilter,          // 3. VAD 说话检测（HTTP，最慢）
];

export const pushDispatcherHooks = {
  async shouldSkipPushQueueItem(): Promise<boolean> {
    return false;
  },
};

export async function runPushDispatcher(sessionId: string): Promise<void> {
  const pendingItems = await getPendingPushQueue(sessionId);
  const reservedUsers = new Set<string>();

  if (pendingItems.length === 0) {
    return;
  }

  logger.info(`push dispatcher pending=${pendingItems.length}`, { sessionId });

  for (const item of pendingItems) {
    try {
      if (await pushDispatcherHooks.shouldSkipPushQueueItem()) {
        await updatePushQueueStatus(item.id, 'skipped');
        logger.info(`push skipped by hook queue_id=${item.id} user=${item.target_user_id}`, { sessionId });
        continue;
      }

      const outcome = await runPushFilterChain(
        { sessionId, item, reservedUsers },
        PUSH_FILTERS,
      );

      if (outcome.action === 'skip') {
        await updatePushQueueStatus(item.id, 'skipped');
        logger.info(
          `push skipped queue_id=${item.id} user=${item.target_user_id} by=${outcome.by} reason=${outcome.reasonCode}`,
          { sessionId },
        );
        continue;
      }

      if (outcome.action === 'defer') {
        // 保留 pending 状态，下一个 dispatcher 周期自动重试
        logger.info(
          `push deferred queue_id=${item.id} user=${item.target_user_id} by=${outcome.by} reason=${outcome.reasonCode}`,
          { sessionId },
        );
        continue;
      }

      // outcome.action === 'proceed' → 执行推送
      const stateId = await writeDiscussionState({
        session_id: item.session_id,
        state_type: item.state_type,
        target_user_id: item.target_user_id,
        trigger_metrics: { queued_push_id: item.id },
        window_start: item.analysis_window_start,
      });

      const deliveredAt = new Date();
      await writePushLog({
        session_id: item.session_id,
        state_id: stateId,
        target_user_id: item.target_user_id,
        push_content: item.push_content,
        content_embedding: item.content_embedding,
        push_channel: 'glasses',
        delivery_status: 'delivered',
        delivered_at: deliveredAt,
      });

      await notifyPush(
        item.session_id,
        item.target_user_id,
        item.push_content,
        stateId,
        item.state_type,
      );

      reservedUsers.add(item.target_user_id);
      await updatePushQueueStatus(item.id, 'delivered', deliveredAt);
      logger.info(`push delivered queue_id=${item.id} user=${item.target_user_id}`, { sessionId });
    } catch (err) {
      logger.error(`push dispatch failed queue_id=${item.id}`, {
        sessionId,
        message: (err as Error).message,
      });
      await updatePushQueueStatus(item.id, 'failed');
    }
  }
}
