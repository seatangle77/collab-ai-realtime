import type { FilterContext, FilterOutcome } from '../types';

/**
 * 同轮去重：同一个 dispatcher 执行周期内，若该用户已有一条推送进入投递流程，
 * 则跳过后续针对该用户的所有推送，防止同一轮次重复打扰。
 */
export async function sameRoundDedupFilter(ctx: FilterContext): Promise<FilterOutcome> {
  const { item, reservedUsers } = ctx;

  if (reservedUsers.has(item.target_user_id)) {
    return {
      action: 'skip',
      by: 'sameRoundDedupFilter',
      reasonCode: 'same_round_dedup',
      reasonText: `user ${item.target_user_id} already has a push in this round`,
    };
  }

  return { action: 'proceed' };
}
