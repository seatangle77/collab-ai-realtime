import type { PushQueueRow } from '../../db/queries';

// ── 过滤结果 reasonCode ───────────────────────────────────────────────────────

export type FilterReasonCode =
  | 'same_round_dedup'    // 同轮已向该用户推送过
  | 'content_similarity'  // 与近期推送内容相似度超阈值
  | 'vad_speaking'        // 当前有人正在说话，推送延迟
  | 'hook_skip';          // 外部 hook 决定跳过

// ── 过滤链 Outcome ────────────────────────────────────────────────────────────

export type FilterOutcome =
  | { action: 'proceed' }
  | {
      action: 'skip';
      by: string;           // 决策 filter 的名称，便于排查
      reasonCode: FilterReasonCode;
      reasonText?: string;
    }
  | {
      action: 'defer';      // 留 pending，下一个 dispatcher 周期重试
      by: string;
      reasonCode: FilterReasonCode;
      reasonText?: string;
    };

// ── Filter 执行上下文 ─────────────────────────────────────────────────────────

export interface FilterContext {
  sessionId: string;
  item: PushQueueRow;
  reservedUsers: Set<string>; // 本轮已推送用户（same-round dedup 用）
}

// ── Filter 函数签名 ───────────────────────────────────────────────────────────

/**
 * 每个 filter 只负责判定，不写库、不发通知。
 * 报错时由 run-push-filter-chain 统一兜底为 defer。
 */
export type PushFilter = (ctx: FilterContext) => Promise<FilterOutcome>;
