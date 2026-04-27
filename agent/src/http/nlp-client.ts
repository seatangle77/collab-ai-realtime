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

export interface KeywordRecallItem {
  word: string;
  needs_prompt: boolean;
  target_user_id: string;
  reason: string;
}

export interface KeywordRecallWithGapResult {
  keywords: KeywordRecallItem[];
}

export interface ReasoningResult {
  has_reasoning: boolean;
  has_evidence: boolean;
  method: string;
}

export interface MemberReasoningResult {
  user_id: string;
  reasoning_status: boolean | null;
  evidence_status: boolean | null;
  reasoning_source: string;
  evidence_source: string;
}

export interface AssessGapParams {
  keywords?: string[];
  summary?: string;
  member_texts: Record<string, string>;
  skw_scores?: Record<string, number>;
}

export interface AssessGapItem {
  keyword: string;
  needs_prompt: boolean;
  target_user_id: string;
  gap_type: string;
  confidence: number;
  reason: string;
  skw_score?: number;
}

export interface AssessGapResult {
  items: AssessGapItem[];
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

/** 关键词召回 + 信息缺口评估（一次大模型调用） */
export async function keywordRecallWithGap(
  memberTexts: Record<string, string>,
): Promise<KeywordRecallWithGapResult> {
  try {
    const res = await client.post<KeywordRecallWithGapResult>('/api/nlp/keyword_recall_with_gap', {
      member_texts: memberTexts,
    }, { timeout: 60_000 });
    return res.data;
  } catch (err) {
    logger.error('keyword_recall_with_gap failed', { message: (err as Error).message });
    return { keywords: [] };
  }
}

/** 宽松 TF-IDF 关键词提取，供 info_gain 使用 */
export async function extractKeywordsBroad(texts: string[], topN = 10): Promise<string[]> {
  if (texts.length === 0) return [];
  try {
    const res = await client.post<{ keywords: string[] }>(
      '/api/nlp/extract_keywords_broad',
      { texts, top_n: topN },
      { timeout: 30_000 },
    );
    return res.data.keywords ?? [];
  } catch (err) {
    logger.error('extract_keywords_broad failed', { message: (err as Error).message });
    return [];
  }
}

/** 全员批量论证结构判定（主分析链路用），失败时返回空数组 */
export async function reasoningBatch(
  members: Array<{ user_id: string; text: string }>,
): Promise<MemberReasoningResult[]> {
  if (members.length === 0) return [];
  try {
    const res = await client.post<{ members: MemberReasoningResult[] }>(
      '/api/nlp/reasoning_batch',
      { members },
      { timeout: 30_000 },
    );
    return res.data.members ?? [];
  } catch (err) {
    logger.error('reasoning_batch failed', { message: (err as Error).message });
    return [];
  }
}

/** 信息缺口评估（Rubric） */
export async function assessGap(
  params: AssessGapParams,
): Promise<AssessGapItem[]> {
  try {
    const res = await client.post<AssessGapResult>(
      '/api/nlp/assess_gap',
      params,
      { timeout: 45_000 },
    );
    return res.data.items ?? [];
  } catch (err) {
    logger.error('assess_gap failed', { message: (err as Error).message });
    return [];
  }
}

export interface GroupSilenceResult {
  content: string;
}

export interface MemberMetricsInput {
  user_id: string;
  speaking_ratio: number;
  silence_s: number;
  ttr: number | null;
  arg_density: number | null;
  srep: number | null;
  info_gain: number | null;
  reasoning_status: boolean | null;
  evidence_status: boolean | null;
  reasoning_source: string | null;
  evidence_source: string | null;
}

export interface AnalyzeMembersTranscriptInput {
  transcript_id: string;
  user_id: string;
  speaker_name: string;
  text: string;
}

export interface MemberAnalysisItem {
  user_id: string;
  challenge_type: 'stagnation' | 'shallow' | 'none';
  needs_prompt: boolean;
  analysis: string;
  content: string;
  anchor: {
    transcript_id: string;
    speaker_id: string;
    speaker_name: string;
    text: string;
  } | null;
}

export interface AnalyzeMembersResult {
  members: MemberAnalysisItem[];
}

export interface NotifyPushResult {
  id: string | null;
  delivery_status: 'pending' | 'delivered' | 'failed' | 'skipped' | 'deferred';
  delivery_reason: string | null;
  ws_sent: boolean;
}

/** fast_model：为群体沉默生成一句破冰话题 */
export async function generateGroupSilence(params: {
  summary: string;
  transcripts: string;
  silence_s: number;
}): Promise<string> {
  try {
    const res = await client.post<GroupSilenceResult>(
      '/api/nlp/generate_group_silence',
      params,
      { timeout: 15_000 },
    );
    return res.data.content ?? '';
  } catch (err) {
    logger.error('generate_group_silence failed', { message: (err as Error).message });
    return '';
  }
}

/** heavy_model：对所有成员做一次批量分析，返回大JSON */
export async function analyzeMembers(params: {
  summary: string;
  transcripts: AnalyzeMembersTranscriptInput[];
  members: MemberMetricsInput[];
}): Promise<MemberAnalysisItem[]> {
  try {
    const res = await client.post<AnalyzeMembersResult>(
      '/api/nlp/analyze_members',
      params,
      { timeout: 60_000 },
    );
    return res.data.members ?? [];
  } catch (err) {
    logger.error('analyze_members failed', { message: (err as Error).message });
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
): Promise<NotifyPushResult> {
  try {
    const res = await client.post<NotifyPushResult>(`/api/internal/sessions/${sessionId}/push-notify`, {
      target_user_id: targetUserId,
      content,
      state_id: stateId ?? null,
      trigger_type: triggerType ?? '',
      queue_id: queueId ?? null,
    });
    return res.data;
  } catch (err) {
    logger.error('notify_push failed', { message: (err as Error).message });
    throw err;
  }
}

/** 发送群组沉默广播 */
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
