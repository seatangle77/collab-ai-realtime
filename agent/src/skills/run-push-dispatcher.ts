import { createLogger } from '../logger';
import {
  getRecentDeliveredEmbeddings,
  getStateTypeCountInWindow,
  getPendingPushQueue,
  updatePushQueueStatus,
  writeDiscussionState,
  writePushLog,
} from '../db/queries';
import { notifyPush } from '../http/nlp-client';

const logger = createLogger('push-dispatcher');
const SIMILARITY_THRESHOLD = 0.6;
// 暂定 0.6，后续根据实测效果考虑调整至 0.65 或 0.7

export const pushDispatcherHooks = {
  async shouldSkipPushQueueItem(): Promise<boolean> {
    return false;
  },
};

export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length === 0 || b.length === 0 || a.length !== b.length) {
    return 0;
  }

  let dot = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < a.length; i += 1) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  if (normA === 0 || normB === 0) {
    return 0;
  }

  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

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
        logger.info(`push skipped queue_id=${item.id} user=${item.target_user_id}`, { sessionId });
        continue;
      }

      if (reservedUsers.has(item.target_user_id)) {
        await updatePushQueueStatus(item.id, 'skipped');
        logger.info(`push skipped by same-round dedupe queue_id=${item.id} user=${item.target_user_id}`, { sessionId });
        continue;
      }

      const deliveredCount = await getStateTypeCountInWindow(
        item.session_id,
        item.target_user_id,
        item.state_type,
      );
      if (deliveredCount >= 2) {
        await updatePushQueueStatus(item.id, 'skipped');
        logger.info(`push skipped by frequency limit queue_id=${item.id} user=${item.target_user_id}`, {
          sessionId,
          deliveredCount,
        });
        continue;
      }

      const recentEmbeddings = await getRecentDeliveredEmbeddings(
        item.session_id,
        item.target_user_id,
        item.state_type,
        2,
      );
      const hitSimilarityThreshold = recentEmbeddings.some((history) => (
        cosineSimilarity(item.content_embedding, history.content_embedding) >= SIMILARITY_THRESHOLD
      ));
      if (hitSimilarityThreshold) {
        await updatePushQueueStatus(item.id, 'skipped');
        logger.info(`push skipped by content similarity queue_id=${item.id} user=${item.target_user_id}`, {
          sessionId,
        });
        continue;
      }

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
