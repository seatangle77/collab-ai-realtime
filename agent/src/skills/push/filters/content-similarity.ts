import { getRecentDeliveredEmbeddings } from '../../../db/queries';
import type { FilterContext, FilterOutcome } from '../types';

const SIMILARITY_THRESHOLD = 0.6;
// 暂定 0.6，后续根据实测效果考虑调整至 0.65 或 0.7

/**
 * 计算两个向量的余弦相似度，任一为空向量时返回 0。
 */
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

/**
 * 内容相似度过滤：与该用户最近 2 条已投递推送的语义相似度超过阈值时跳过，
 * 避免跨轮次、跨端重复推送近似内容。
 */
export async function contentSimilarityFilter(ctx: FilterContext): Promise<FilterOutcome> {
  const { item } = ctx;

  const recentEmbeddings = await getRecentDeliveredEmbeddings(
    item.session_id,
    item.target_user_id,
    ['stagnation', 'shallow'],
    2,
  );

  const hitThreshold = recentEmbeddings.some(
    (history) => cosineSimilarity(item.content_embedding, history.content_embedding) >= SIMILARITY_THRESHOLD,
  );

  if (hitThreshold) {
    return {
      action: 'skip',
      by: 'contentSimilarityFilter',
      reasonCode: 'content_similarity',
      reasonText: `embedding similarity >= ${SIMILARITY_THRESHOLD} with recent delivered push`,
    };
  }

  return { action: 'proceed' };
}
