import { createLogger } from '../../logger';
import type { FilterContext, FilterOutcome, PushFilter } from './types';

const logger = createLogger('push-filter-chain');

/**
 * 按顺序执行 filter 列表，遇到第一个非 proceed 结果立即返回。
 * 单个 filter 抛出异常时，统一兜底为 defer（保留 pending，下轮重试），
 * 防止 transient error 误杀推送。
 *
 * 推荐执行顺序（先便宜后昂贵）：
 *   sameRoundDedupFilter → contentSimilarityFilter → vadCheckFilter
 */
export async function runPushFilterChain(
  ctx: FilterContext,
  filters: PushFilter[],
): Promise<FilterOutcome> {
  for (const filter of filters) {
    let result: FilterOutcome;

    try {
      result = await filter(ctx);
    } catch (err) {
      logger.error(`filter threw, deferring push`, {
        sessionId: ctx.sessionId,
        queueId: ctx.item.id,
        filterName: filter.name,
        message: (err as Error).message,
      });
      return {
        action: 'defer',
        by: filter.name,
        reasonCode: 'hook_skip',
        reasonText: (err as Error).message,
      };
    }

    if (result.action !== 'proceed') {
      logger.info(`push filter decision: ${result.action}`, {
        sessionId: ctx.sessionId,
        queueId: ctx.item.id,
        by: result.by,
        reasonCode: result.reasonCode,
        reasonText: result.reasonText,
      });
      return result;
    }
  }

  return { action: 'proceed' };
}
