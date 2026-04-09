import { checkVadSpeaking } from '../../../http/nlp-client';
import type { FilterContext, FilterOutcome } from '../types';

/**
 * VAD 说话检测：推送前查询当前 session 是否有人正在说话。
 * 有人说话时返回 defer（保留 pending 状态），等下一个 dispatcher 周期再试，
 * 避免在用户发言过程中弹出 AI 提示打断思路。
 *
 * 注意：checkVadSpeaking 内部已做异常兜底（返回 false），
 * 此处额外的 try/catch 由 run-push-filter-chain 统一处理。
 */
export async function vadCheckFilter(ctx: FilterContext): Promise<FilterOutcome> {
  const { sessionId, item } = ctx;

  const isSpeaking = await checkVadSpeaking(sessionId);

  if (isSpeaking) {
    return {
      action: 'defer',
      by: 'vadCheckFilter',
      reasonCode: 'vad_speaking',
      reasonText: `session ${sessionId} has active speech, push deferred`,
    };
  }

  return { action: 'proceed' };
}
