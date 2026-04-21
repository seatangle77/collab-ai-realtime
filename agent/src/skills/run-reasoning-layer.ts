// 硬阈值触发逻辑已废弃，保留类型供后续 heavy_model 统一分析使用

export type TriggerType =
  | 'group_silence'
  | 'stagnation'
  | 'shallow'
  | 'info_gap';

export interface Trigger {
  type: TriggerType;
  userId?: string;
  targetUsers: string[];
  keyword?: string;
  skwScore?: number;
  triggerMetrics: Record<string, unknown>;
}
