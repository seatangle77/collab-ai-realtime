import axios, { AxiosInstance } from 'axios';
import { config } from '../config';
import { createLogger } from '../logger';

const logger = createLogger('nlp-client');

// ── 响应类型 ──────────────────────────────────────────────────────────────────

export interface SegmentResult {
  tokens: string[];
  token_count: number;
  unique_count: number;
  ttr: number;
  arg_density: number;
}

export interface EmbedResult {
  embeddings: number[][];
}

export interface SimilarityResult {
  scores: number[];
}

export interface TfidfResult {
  keywords: string[];
  member_keyword_contexts: Record<string, Record<string, string>>;
}

export interface ReasoningResult {
  has_reasoning: boolean;
  has_evidence: boolean;
  method: string;
}

export interface GeneratePushParams {
  trigger_type: string;
  summary?: string;
  transcripts?: string;
  username?: string;
  silence_s?: number;
  speaking_ratio?: number;
  triggered_metrics?: string;
  keyword?: string;
  skw_score?: number;
}

export type ChallengeType =
  | 'personal_stagnation'
  | 'group_stagnation'
  | 'shallow_expression'
  | 'information_gap'
  | 'none';

export interface BatchMemberInput {
  user_id: string;
}

export interface BatchTargetInput {
  user_id: string;
  challenge_type: ChallengeType;
  evidence: Record<string, unknown>;
  diagnosis: string;
  design_goal: string;
}

export interface BatchGeneratePushAnalysisParams {
  session_id: string;
  summary: string;
  transcripts: string;
  members: BatchMemberInput[];
  targets: BatchTargetInput[];
}

export interface BatchAnalysisItem {
  user_id: string;
  challenge_type: ChallengeType;
  needs_prompt: boolean;
  analysis: string;
  content: string;
}

export interface BatchGeneratePushAnalysisResult {
  items: BatchAnalysisItem[];
}

export interface TranscriptItem {
  user_id: string;
  text: string;
}

// ── 客户端 ────────────────────────────────────────────────────────────────────

function createNlpClient(): AxiosInstance {
  return axios.create({
    baseURL: config.nlp.baseUrl,
    headers: {
      'X-Admin-Token': config.nlp.adminToken,
      'Content-Type': 'application/json',
    },
    timeout: 30_000,
  });
}

const client = createNlpClient();

// ── 接口封装 ──────────────────────────────────────────────────────────────────

/** 中文分词 + TTR + arg_density */
export async function segment(text: string): Promise<SegmentResult> {
  try {
    const res = await client.post<SegmentResult>('/api/nlp/segment', { text });
    return res.data;
  } catch (err) {
    logger.error('segment failed', { message: (err as Error).message });
    throw err;
  }
}

/** 批量文本向量化 */
export async function embed(texts: string[]): Promise<number[][]> {
  if (texts.length === 0) return [];
  try {
    const res = await client.post<EmbedResult>('/api/nlp/embed', { texts });
    return res.data.embeddings;
  } catch (err) {
    logger.error('embed failed', { message: (err as Error).message });
    throw err;
  }
}

/** 批量余弦相似度，pairs 数组长度和返回 scores 数组长度一致 */
export async function similarity(
  pairs: Array<{ vec_a: number[]; vec_b: number[] }>,
): Promise<number[]> {
  if (pairs.length === 0) return [];
  try {
    const res = await client.post<SimilarityResult>('/api/nlp/similarity', { pairs });
    return res.data.scores;
  } catch (err) {
    logger.error('similarity failed', { message: (err as Error).message });
    throw err;
  }
}

/** TF-IDF 关键词提取，memberTexts = { user_id: 发言文本 } */
export async function tfidf(
  memberTexts: Record<string, string>,
  topN = 5,
): Promise<TfidfResult> {
  try {
    const res = await client.post<TfidfResult>('/api/nlp/tfidf', {
      member_texts: memberTexts,
      top_n: topN,
    });
    return res.data;
  } catch (err) {
    logger.error('tfidf failed', { message: (err as Error).message });
    throw err;
  }
}

/** 判断文本是否含论证结构 */
export async function hasReasoning(text: string): Promise<ReasoningResult> {
  try {
    const res = await client.post<ReasoningResult>('/api/nlp/has_reasoning', { text }, { timeout: 30_000 });
    return res.data;
  } catch (err) {
    logger.error('has_reasoning failed', { message: (err as Error).message });
    throw err;
  }
}

/** 生成推送文案，失败时返回空字符串 */
export async function generatePush(params: GeneratePushParams): Promise<string> {
  try {
    const res = await client.post<{ content: string }>('/api/nlp/generate_push', params, { timeout: 30_000 });
    return res.data.content ?? '';
  } catch (err) {
    logger.error('generate_push failed', { message: (err as Error).message });
    return '';
  }
}

/** 批量生成成员分析结果，失败时返回空数组 */
export async function generatePushBatchAnalysis(
  params: BatchGeneratePushAnalysisParams,
): Promise<BatchAnalysisItem[]> {
  try {
    const res = await client.post<BatchGeneratePushAnalysisResult>(
      '/api/nlp/generate_push_batch',
      params,
      { timeout: 45_000 },
    );
    return res.data.items ?? [];
  } catch (err) {
    logger.error('generate_push_batch failed', { message: (err as Error).message });
    return [];
  }
}

/** 将推送文案提交给后端写库并通过 WebSocket 定向发给目标用户 */
export async function notifyPush(
  sessionId: string,
  targetUserId: string,
  content: string,
  stateId?: string,
  triggerType?: string,
  queueId?: string,
): Promise<void> {
  try {
    await client.post(`/api/internal/sessions/${sessionId}/push-notify`, {
      target_user_id: targetUserId,
      content,
      state_id: stateId ?? null,
      trigger_type: triggerType ?? '',
      queue_id: queueId ?? null,
    });
  } catch (err) {
    logger.error('notify_push failed', { message: (err as Error).message });
  }
}

/** 发送群组沉默广播（target_user_id='ALL'） */
export async function notifyGroupSilence(
  sessionId: string,
  content: string,
): Promise<boolean> {
  try {
    await client.post(`/api/internal/sessions/${sessionId}/group-notify`, { content });
    return true;
  } catch (err) {
    logger.error('notify_group_silence failed', { message: (err as Error).message });
    return false;
  }
}

/** 通知后端将新 info_gap 按钮通过 WebSocket 推给目标用户 */
export async function notifyInfoGapButton(params: {
  session_id: string;
  user_id: string;
  button_id: string;
  keyword: string;
  skw_score: number;
  window_start: string;
}): Promise<void> {
  try {
    await client.post(`/api/internal/sessions/${params.session_id}/info-gap/notify`, {
      user_id: params.user_id,
      button_id: params.button_id,
      keyword: params.keyword,
      skw_score: params.skw_score,
      window_start: params.window_start,
    });
  } catch (err) {
    logger.error('notify_info_gap_button failed', { message: (err as Error).message });
  }
}

/** 将生成的摘要提交给后端写库并触发 WebSocket 广播，失败时抛出异常 */
export async function notifySummary(
  sessionId: string,
  content: string,
  windowStart: Date,
  windowEnd: Date,
): Promise<void> {
  try {
    await client.post(`/api/internal/sessions/${sessionId}/summary`, {
      content,
      window_start: windowStart.toISOString(),
      window_end: windowEnd.toISOString(),
    });
  } catch (err) {
    logger.error('notify_summary failed', { message: (err as Error).message });
    throw err;
  }
}

/** 生成滚动摘要，失败时返回空字符串 */
export async function generateSummary(
  transcripts: TranscriptItem[],
  prevSummary = '',
): Promise<string> {
  try {
    const res = await client.post<{ summary: string }>('/api/nlp/generate_summary', {
      transcripts,
      prev_summary: prevSummary,
    }, { timeout: 45_000 });
    return res.data.summary ?? '';
  } catch (err) {
    logger.error('generate_summary failed', { message: (err as Error).message });
    return '';
  }
}

/**
 * 查询当前 session 是否有人正在说话（VAD 信号）。
 * 推送前调用，有人说话时跳过本次推送。
 * 出错时返回 false，不阻塞推送。
 */
export async function checkVadSpeaking(sessionId: string): Promise<boolean> {
  try {
    const res = await client.get<{ is_speaking: boolean }>(
      `/api/internal/sessions/${sessionId}/vad-speaking`,
      { timeout: 2_000 },
    );
    return res.data.is_speaking ?? false;
  } catch (err) {
    logger.warn('check_vad_speaking failed, defaulting to false', { message: (err as Error).message });
    return false;
  }
}
