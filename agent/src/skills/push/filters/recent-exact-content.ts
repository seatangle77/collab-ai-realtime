import { hasRecentDeliveredPushWithExactContent } from '../../../db/queries';
import type { FilterContext, FilterOutcome } from '../types';

const RECENT_EXACT_CONTENT_WINDOW_MS = 10 * 60 * 1000;

/**
 * 短时间硬去重：同一用户近期若已收到完全相同的文案，则直接跳过。
 * 这层规则比 embedding 相似度更便宜，也能兜住跨轮次重复生成的相同文案。
 */
export async function recentExactContentFilter(ctx: FilterContext): Promise<FilterOutcome> {
  const { item } = ctx;

  const exists = await hasRecentDeliveredPushWithExactContent(
    item.session_id,
    item.target_user_id,
    item.push_content,
    RECENT_EXACT_CONTENT_WINDOW_MS,
  );

  if (exists) {
    return {
      action: 'skip',
      by: 'recentExactContentFilter',
      reasonCode: 'recent_exact_content',
      reasonText: 'same push content was already delivered to this user recently',
    };
  }

  return { action: 'proceed' };
}
