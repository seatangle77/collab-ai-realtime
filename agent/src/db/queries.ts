import { pool } from './client';
import { nanoid } from 'nanoid';
import { createLogger } from '../logger';

const logger = createLogger('db-queries');

// ── 共享类型 ──────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  group_id: string;
  status: string;
  started_at: Date | null;
}

export interface SessionMember {
  user_id: string;
}

export interface Transcript {
  transcript_id: string;
  user_id: string | null;
  speaker_name: string | null;
  text: string | null;
  start: Date;
  end: Date;
  duration: number | null;
}

export interface WindowMetricsRow {
  session_id: string;
  user_id: string;
  window_start: Date;
  window_end: Date;
  speaking_ratio: number;
  silence_s: number;
  ttr: number | null;
  arg_density: number | null;
  srep: number | null;
  info_gain: number | null;
  has_reasoning: boolean | null;
  has_evidence: boolean | null;
  reasoning_source: string | null;
  evidence_source: string | null;
}

export interface KeywordSkwRow {
  session_id: string;
  window_start: Date;
  keyword: string;
  user_a_id?: string;
  user_b_id?: string;
  skw_score?: number;
  mention_count?: number;
  skw_status?: string;
}

export interface HistoricalKeyword {
  keyword: string;
}

export interface PushQueueRow {
  id: string;
  session_id: string;
  target_user_id: string;
  state_type: string;
  push_content: string;
  content_embedding: number[];
  analysis_window_start: Date;
  status: 'pending' | 'processing' | 'delivered' | 'skipped' | 'failed' | 'deferred';
  created_at: Date;
  delivered_at: Date | null;
}

export interface DiscussionStateRow {
  id: string;
  session_id: string;
  state_type: string;
  target_user_id: string | null;
  trigger_metrics: Record<string, unknown> | null;
  window_start: Date | null;
}

const MEMBER_INTERVENTION_STATE_TYPES = ['stagnation', 'shallow'] as const;

// ── 工具函数 ──────────────────────────────────────────────────────────────────

/**
 * 将 JS Date 转为无时区的 UTC 字符串（如 "2026-04-03 07:55:13.000"）
 * DB 里的 timestamp without time zone 存的是 UTC 裸值，
 * 传参时必须也用裸 UTC 字符串，否则 pg 会先把 Date 转成本地时间再比较，
 * 导致 UTC+8 环境下出现 8 小时偏移。
 */
function toUtcString(date: Date): string {
  return date.toISOString().replace('T', ' ').replace('Z', '');
}

function toPgVectorLiteral(vector: number[]): string {
  return `[${vector.join(',')}]`;
}

function parsePgVector(value: unknown): number[] {
  if (Array.isArray(value)) {
    return value.map((item) => Number(item));
  }

  if (typeof value !== 'string') {
    return [];
  }

  const trimmed = value.trim();
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) {
    return [];
  }

  const body = trimmed.slice(1, -1).trim();
  if (!body) {
    return [];
  }

  return body.split(',').map((item) => Number(item.trim()));
}

// ── 查询函数 ──────────────────────────────────────────────────────────────────

/** 获取所有 ongoing 会话 */
export async function getOngoingSessions(): Promise<Session[]> {
  const res = await pool.query<Session>(
    `SELECT id, group_id, status, started_at
     FROM chat_sessions
     WHERE status = 'ongoing'
       AND active_ws_count > 0`,
  );
  return res.rows;
}

/** 获取会话的所有活跃成员 */
export async function getSessionMembers(sessionId: string): Promise<SessionMember[]> {
  const res = await pool.query<SessionMember>(
    `SELECT DISTINCT gm.user_id
     FROM group_memberships gm
     JOIN chat_sessions cs ON cs.group_id = gm.group_id
     WHERE cs.id = $1
       AND gm.status = 'active'`,
    [sessionId],
  );
  return res.rows;
}

/** 获取指定时间窗口内的转写记录 */
export async function getTranscriptsInWindow(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
): Promise<Transcript[]> {
  const res = await pool.query<Transcript>(
    `SELECT t.transcript_id,
            COALESCE(NULLIF(t.user_id, ''), NULLIF(t.speaker, ''), NULLIF(t.speaker, 'unknown')) AS user_id,
            u.name AS speaker_name,
            t.text, t.start, t."end", t.duration
     FROM speech_transcripts t
     LEFT JOIN users_info u
            ON u.id = COALESCE(NULLIF(t.user_id, ''), NULLIF(t.speaker, ''))
     WHERE t.session_id = $1
       AND t.start >= $2
       AND t.start < $3
       AND t.text IS NOT NULL
       AND t.text != ''
     ORDER BY t.start ASC`,
    [sessionId, toUtcString(windowStart), toUtcString(windowEnd)],
  );
  return res.rows;
}

/** 优先从 Redis 读取最近窗口转写，失败或无结果时回退数据库 */
export async function getTranscriptsInWindowPreferCache(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
): Promise<Transcript[]> {
  const { getCachedTranscriptsInWindow } = await import('../cache/transcript-cache');
  const cached = await getCachedTranscriptsInWindow(sessionId, windowStart, windowEnd);
  const dbRows = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  if (cached.length === 0) {
    logger.info('transcript cache miss, using db window', {
      sessionId,
      count: dbRows.length,
      windowStart: windowStart.toISOString(),
      windowEnd: windowEnd.toISOString(),
    });
    return dbRows;
  }

  const cachedIds = cached.map((item) => item.transcript_id).join(',');
  const dbIds = dbRows.map((item) => item.transcript_id).join(',');
  if (cachedIds !== dbIds) {
    logger.warn('transcript cache coverage mismatch, using db window', {
      sessionId,
      cached_count: cached.length,
      db_count: dbRows.length,
      windowStart: windowStart.toISOString(),
      windowEnd: windowEnd.toISOString(),
    });
    return dbRows;
  }

  logger.info('using transcript cache window', {
    sessionId,
    count: cached.length,
    windowStart: windowStart.toISOString(),
    windowEnd: windowEnd.toISOString(),
  });
  return cached;
}

/** 获取指定 session 最近一次 end 时间（用于 silence 检测） */
export async function getLastSpeakEndPerUser(
  sessionId: string,
  since: Date,
): Promise<Array<{ user_id: string; last_end: Date }>> {
  const res = await pool.query<{ user_id: string; last_end: Date }>(
    `SELECT COALESCE(NULLIF(user_id, ''), NULLIF(speaker, ''), NULLIF(speaker, 'unknown')) AS user_id,
            MAX("end") AS last_end
     FROM speech_transcripts
     WHERE session_id = $1
       AND "end" >= $2
       AND COALESCE(NULLIF(user_id, ''), NULLIF(speaker, ''), NULLIF(speaker, 'unknown')) IS NOT NULL
     GROUP BY COALESCE(NULLIF(user_id, ''), NULLIF(speaker, ''), NULLIF(speaker, 'unknown'))`,
    [sessionId, toUtcString(since)],
  );
  return res.rows;
}

/** 获取 session 全局最近一条转写创建时间（群体沉默检测用） */
export async function getLastSpeakEndGlobal(
  sessionId: string,
): Promise<Date | null> {
  const res = await pool.query<{ last_end: Date | null }>(
    `SELECT MAX(created_at) AS last_end
     FROM speech_transcripts
     WHERE session_id = $1`,
    [sessionId],
  );
  return res.rows[0]?.last_end ?? null;
}

/** 写入当前窗口的宽松 TF-IDF 关键词（供 info_gain 历史对比使用，按成员存储） */
export async function writeWindowMetricsKeywords(
  sessionId: string,
  userId: string,
  windowStart: Date,
  keywords: string[],
): Promise<void> {
  if (keywords.length === 0) return;
  const values = keywords
    .map((_, i) => `('wmk_' || substr(md5(random()::text), 1, 12), $1, $2, $3, $${i + 4}, NOW())`)
    .join(', ');
  await pool.query(
    `INSERT INTO window_metrics_keywords (id, session_id, user_id, window_start, keyword, created_at)
     VALUES ${values}
     ON CONFLICT DO NOTHING`,
    [sessionId, userId, toUtcString(windowStart), ...keywords],
  );
}

/** 获取历史窗口中的宽松关键词（info_gain 对比用，只取指定成员最近2个窗口内的关键词） */
export async function getHistoricalWindowMetricsKeywords(
  sessionId: string,
  userId: string,
  before: Date,
  historyStart: Date,
): Promise<HistoricalKeyword[]> {
  const res = await pool.query<HistoricalKeyword>(
    `SELECT DISTINCT keyword
     FROM window_metrics_keywords
     WHERE session_id = $1
       AND user_id = $2
       AND window_start >= $3
       AND window_start < $4`,
    [sessionId, userId, toUtcString(historyStart), toUtcString(before)],
  );
  return res.rows;
}

/** 写入 window_metrics（批量，一次一个 user） */
export async function writeWindowMetrics(row: WindowMetricsRow): Promise<void> {
  const id = 'wm_' + nanoid(12);
  await pool.query(
    `INSERT INTO window_metrics
       (id, session_id, user_id, window_start, window_end,
        speaking_ratio, silence_s, ttr, arg_density,
        srep, info_gain, has_reasoning, has_evidence,
        reasoning_source, evidence_source, created_at)
     VALUES
       ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW())`,
    [
      id,
      row.session_id,
      row.user_id,
      toUtcString(row.window_start),
      toUtcString(row.window_end),
      row.speaking_ratio,
      row.silence_s,
      row.ttr,
      row.arg_density,
      row.srep,
      row.info_gain,
      row.has_reasoning,
      row.has_evidence,
      row.reasoning_source,
      row.evidence_source,
    ],
  );
}

// ── 推理层 / 行动层 / 摘要层 新增查询 ─────────────────────────────────────────

/** 写入 discussion_states，返回生成的 id */
export async function writeDiscussionState(row: {
  session_id: string;
  state_type: string;
  target_user_id?: string;
  trigger_metrics: Record<string, unknown>;
  window_start: Date;
}): Promise<string> {
  const id = 'ds_' + nanoid(12);
  await pool.query(
    `INSERT INTO discussion_states
       (id, session_id, state_type, target_user_id, trigger_metrics,
        window_start, triggered_at)
     VALUES ($1, $2, $3, $4, $5, $6, NOW())`,
    [
      id,
      row.session_id,
      row.state_type,
      row.target_user_id ?? null,
      JSON.stringify(row.trigger_metrics),
      toUtcString(row.window_start),
    ],
  );
  return id;
}

export async function findDiscussionStateByQueuedPushId(params: {
  sessionId: string;
  queueId: string;
}): Promise<DiscussionStateRow | null> {
  const res = await pool.query<{
    id: string;
    session_id: string;
    state_type: string;
    target_user_id: string | null;
    trigger_metrics: Record<string, unknown> | string | null;
    window_start: Date | null;
  }>(
    `SELECT id, session_id, state_type, target_user_id, trigger_metrics, window_start
     FROM discussion_states
     WHERE session_id = $1
       AND trigger_metrics ->> 'queued_push_id' = $2
     ORDER BY triggered_at DESC
     LIMIT 1`,
    [params.sessionId, params.queueId],
  );

  const row = res.rows[0];
  if (!row) return null;

  let triggerMetrics: Record<string, unknown> | null = null;
  if (typeof row.trigger_metrics === 'string') {
    try {
      triggerMetrics = JSON.parse(row.trigger_metrics) as Record<string, unknown>;
    } catch {
      triggerMetrics = null;
    }
  } else {
    triggerMetrics = row.trigger_metrics;
  }

  return {
    id: row.id,
    session_id: row.session_id,
    state_type: row.state_type,
    target_user_id: row.target_user_id,
    trigger_metrics: triggerMetrics,
    window_start: row.window_start,
  };
}

/** 写入 push_queue，返回生成的 id */
export async function writePushQueueItem(row: {
  session_id: string;
  target_user_id: string;
  state_type: string;
  push_content: string;
  content_embedding: number[];
  analysis_window_start: Date;
}): Promise<string> {
  const id = 'pq_' + nanoid(12);
  await pool.query(
    `INSERT INTO push_queue
       (id, session_id, target_user_id, state_type, push_content,
        content_embedding, analysis_window_start, status, created_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', NOW())`,
    [
      id,
      row.session_id,
      row.target_user_id,
      row.state_type,
      row.push_content,
      row.content_embedding,
      toUtcString(row.analysis_window_start),
    ],
  );
  return id;
}

export async function trimPendingMemberInterventionQueue(params: {
  sessionId: string;
  targetUserId: string;
  keepLatest: number;
}): Promise<number> {
  const res = await pool.query<{ id: string }>(
    `WITH stale AS (
       SELECT id
       FROM push_queue
       WHERE session_id = $1
         AND target_user_id = $2
         AND state_type = ANY($3::text[])
         AND status = 'pending'
       ORDER BY analysis_window_start DESC, created_at DESC
       OFFSET $4
     )
     UPDATE push_queue pq
     SET status = 'skipped'
     FROM stale
     WHERE pq.id = stale.id
     RETURNING pq.id`,
    [params.sessionId, params.targetUserId, MEMBER_INTERVENTION_STATE_TYPES, params.keepLatest],
  );
  return res.rowCount ?? 0;
}

export async function skipOtherPendingMemberInterventionQueueItems(params: {
  sessionId: string;
  targetUserId: string;
  deliveredQueueId: string;
}): Promise<number> {
  const res = await pool.query<{ id: string }>(
    `UPDATE push_queue
     SET status = 'skipped'
     WHERE session_id = $1
       AND target_user_id = $2
       AND state_type = ANY($3::text[])
       AND status = 'pending'
       AND id != $4
     RETURNING id`,
    [params.sessionId, params.targetUserId, MEMBER_INTERVENTION_STATE_TYPES, params.deliveredQueueId],
  );
  return res.rowCount ?? 0;
}

/** 写入 push_logs */
export async function writePushLog(row: {
  session_id: string;
  state_id?: string | null;
  target_user_id: string;
  push_content: string;
  content_embedding: number[];
  push_channel: 'glasses' | 'app' | 'web';
  delivery_status?: 'pending' | 'delivered' | 'failed' | 'skipped' | 'deferred';
  delivery_reason?: string | null;
  delivered_at?: Date;
}): Promise<void> {
  const id = 'pl_' + nanoid(12);
  await pool.query(
    `INSERT INTO push_logs
       (id, session_id, state_id, target_user_id,
        push_content, content_embedding, push_channel, delivery_status, delivery_reason, triggered_at, delivered_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), $10)`,
    [
      id,
      row.session_id,
      row.state_id ?? null,
      row.target_user_id,
      row.push_content,
      row.content_embedding,
      row.push_channel,
      row.delivery_status ?? 'pending',
      row.delivery_reason ?? null,
      row.delivered_at ? toUtcString(row.delivered_at) : null,
    ],
  );
}

/** 读取某 session 下待处理的 push_queue 项 */
export async function getPendingPushQueue(sessionId: string): Promise<PushQueueRow[]> {
  const res = await pool.query<Omit<PushQueueRow, 'content_embedding'> & { content_embedding_raw: string | null }>(
    `SELECT id, session_id, target_user_id, state_type, push_content,
            array_to_json(content_embedding)::text AS content_embedding_raw,
            analysis_window_start, status, created_at, delivered_at
     FROM push_queue
     WHERE session_id = $1
       AND status IN ('pending', 'deferred')
     ORDER BY created_at ASC`,
    [sessionId],
  );
  return res.rows.map((row) => {
    const { content_embedding_raw, ...rest } = row;
    return {
      ...rest,
      content_embedding: parsePgVector(content_embedding_raw),
    };
  });
}

/** 原子地认领某 session 下待处理的 push_queue 项，避免并发 dispatcher 重复消费。 */
export async function claimPendingPushQueue(
  sessionId: string,
  limit = 20,
): Promise<PushQueueRow[]> {
  const res = await pool.query<
    Omit<PushQueueRow, 'content_embedding'> & { content_embedding_raw: string | null }
  >(
    `WITH picked AS (
       SELECT id
     FROM push_queue
     WHERE session_id = $1
         AND status IN ('pending', 'deferred')
         AND (
           state_type != ALL($3::text[])
           OR NOT EXISTS (
             SELECT 1
             FROM push_queue delivered
             WHERE delivered.session_id = push_queue.session_id
               AND delivered.target_user_id = push_queue.target_user_id
               AND delivered.state_type = ANY($3::text[])
               AND delivered.status = 'delivered'
               AND delivered.delivered_at >= NOW() - INTERVAL '120 seconds'
           )
         )
       ORDER BY
         CASE WHEN state_type = ANY($3::text[]) THEN 0 ELSE 1 END,
         CASE WHEN state_type = ANY($3::text[]) THEN analysis_window_start END DESC,
         CASE WHEN state_type = ANY($3::text[]) THEN created_at END DESC,
         created_at ASC
       LIMIT $2
       FOR UPDATE SKIP LOCKED
     )
     UPDATE push_queue pq
     SET status = 'processing'
     FROM picked
     WHERE pq.id = picked.id
     RETURNING
       pq.id, pq.session_id, pq.target_user_id, pq.state_type, pq.push_content,
       array_to_json(pq.content_embedding)::text AS content_embedding_raw,
       pq.analysis_window_start, pq.status, pq.created_at, pq.delivered_at`,
    [sessionId, limit, MEMBER_INTERVENTION_STATE_TYPES],
  );

  return res.rows.map((row) => {
    const { content_embedding_raw, ...rest } = row;
    return {
      ...rest,
      content_embedding: parsePgVector(content_embedding_raw),
    };
  });
}

export async function getRecentDeliveredEmbeddings(
  sessionId: string,
  userId: string,
  stateType: string,
  limit = 2,
): Promise<Array<{ content_embedding: number[] }>> {
  const res = await pool.query<{ content_embedding_raw: string | null }>(
    `SELECT array_to_json(pl.content_embedding)::text AS content_embedding_raw
     FROM push_logs pl
     JOIN discussion_states ds ON ds.id = pl.state_id
     WHERE pl.session_id = $1
       AND pl.target_user_id = $2
       AND ds.state_type = $3
       AND pl.push_channel IN ('web', 'app', 'glasses')
       AND pl.delivery_status = 'delivered'
       AND pl.content_embedding IS NOT NULL
     ORDER BY pl.triggered_at DESC
     LIMIT $4`,
    [sessionId, userId, stateType, limit],
  );

  return res.rows.map((row) => ({
    content_embedding: parsePgVector(row.content_embedding_raw),
  }));
}

export async function hasRecentDeliveredPushWithExactContent(
  sessionId: string,
  userId: string,
  pushContent: string,
  windowMs: number,
): Promise<boolean> {
  const res = await pool.query<{ exists: boolean }>(
    `SELECT EXISTS (
       SELECT 1
       FROM push_logs pl
       WHERE pl.session_id = $1
         AND pl.target_user_id = $2
         AND pl.push_content = $3
         AND pl.push_channel IN ('web', 'app', 'glasses')
         AND pl.delivery_status = 'delivered'
         AND pl.triggered_at >= NOW() - ($4 * INTERVAL '1 millisecond')
     ) AS exists`,
    [sessionId, userId, pushContent, windowMs],
  );

  return Boolean(res.rows[0]?.exists);
}

export async function getStateTypeCountInWindow(
  sessionId: string,
  userId: string,
  stateType: string,
  windowMs = 600_000,
): Promise<number> {
  const res = await pool.query<{ count: string }>(
    `SELECT COUNT(*)::text AS count
     FROM push_queue
     WHERE session_id = $1
       AND target_user_id = $2
       AND state_type = $3
       AND status = 'delivered'
       AND analysis_window_start >= NOW() - ($4 * INTERVAL '1 millisecond')`,
    [sessionId, userId, stateType, windowMs],
  );

  return Number(res.rows[0]?.count ?? '0');
}

/** 更新 push_queue 状态 */
export async function updatePushQueueStatus(
  id: string,
  status: 'pending' | 'processing' | 'delivered' | 'skipped' | 'failed' | 'deferred',
  deliveredAt?: Date,
): Promise<void> {
  if (deliveredAt) {
    await pool.query(
      `UPDATE push_queue
       SET status = $2, delivered_at = $3
       WHERE id = $1`,
      [id, status, toUtcString(deliveredAt)],
    );
    return;
  }

  await pool.query(
    `UPDATE push_queue
     SET status = $2
     WHERE id = $1`,
    [id, status],
  );
}

/** 写入 info_gap_buttons（静默按钮，等待用户点击）。
 *  返回生成的 id；若因 ON CONFLICT 未插入则返回 null。 */
export async function writeInfoGapButton(row: {
  session_id: string;
  user_id: string;
  keyword: string;
  skw_score: number;
  window_start: Date;
  gap_type?: string | null;
  confidence?: number | null;
  llm_reason?: string | null;
}): Promise<string | null> {
  const id = 'igb_' + nanoid(12);
  const res = await pool.query<{ id: string }>(
    `INSERT INTO info_gap_buttons
       (id, session_id, user_id, keyword, skw_score, window_start, status, created_at,
        gap_type, confidence, llm_reason)
     VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW(), $7, $8, $9)
     ON CONFLICT DO NOTHING
     RETURNING id`,
    [
      id,
      row.session_id,
      row.user_id,
      row.keyword,
      row.skw_score,
      toUtcString(row.window_start),
      row.gap_type ?? null,
      row.confidence ?? null,
      row.llm_reason ?? null,
    ],
  );
  return res.rows[0]?.id ?? null;
}

/** 将历史窗口遗留的 pending 按钮标记为 dismissed（视为过期）。 */
export async function dismissPendingInfoGapButtonsBeforeWindow(
  sessionId: string,
  currentWindowStart: Date,
): Promise<number> {
  const res = await pool.query<{ id: string }>(
    `UPDATE info_gap_buttons
     SET status = 'dismissed'
     WHERE session_id = $1
       AND status = 'pending'
       AND window_start < $2
     RETURNING id`,
    [sessionId, toUtcString(currentWindowStart)],
  );
  return res.rowCount ?? 0;
}

/** 是否已存在同 session+user+keyword 的 pending 按钮 */
export async function hasPendingInfoGapKeyword(
  sessionId: string,
  userId: string,
  keyword: string,
): Promise<boolean> {
  const res = await pool.query<{ exists: boolean }>(
    `SELECT EXISTS (
       SELECT 1
       FROM info_gap_buttons
       WHERE session_id = $1
         AND user_id = $2
         AND keyword = $3
         AND status = 'pending'
     ) AS exists`,
    [sessionId, userId, keyword],
  );
  return Boolean(res.rows[0]?.exists);
}

/** 统计当前 pending 按钮数量 */
export async function getPendingInfoGapButtonCount(
  sessionId: string,
  userId: string,
): Promise<number> {
  const res = await pool.query<{ count: string }>(
    `SELECT COUNT(*)::text AS count
     FROM info_gap_buttons
     WHERE session_id = $1
       AND user_id = $2
       AND status = 'pending'`,
    [sessionId, userId],
  );
  return Number(res.rows[0]?.count ?? '0');
}

/** 最近 N 个分析窗口内，该词是否已被点击 */
export async function hasClickedInfoGapKeywordInRecentWindows(
  sessionId: string,
  userId: string,
  keyword: string,
  currentWindowStart: Date,
  recentWindowCount: number,
  windowMs: number,
): Promise<boolean> {
  const since = new Date(currentWindowStart.getTime() - recentWindowCount * windowMs);
  const res = await pool.query<{ exists: boolean }>(
    `SELECT EXISTS (
       SELECT 1
       FROM info_gap_buttons
       WHERE session_id = $1
         AND user_id = $2
         AND keyword = $3
         AND status = 'clicked'
         AND window_start >= $4
     ) AS exists`,
    [sessionId, userId, keyword, toUtcString(since)],
  );
  return Boolean(res.rows[0]?.exists);
}

/** 读取最近一条摘要 */
export async function getLastSummary(
  sessionId: string,
): Promise<{ content: string; window_end: Date } | null> {
  const res = await pool.query<{ content: string; window_end: Date }>(
    `SELECT content, window_end
     FROM discussion_summaries
     WHERE session_id = $1
     ORDER BY window_end DESC
     LIMIT 1`,
    [sessionId],
  );
  return res.rows[0] ?? null;
}

/** 批量更新 info_gap_skw 的 skw_score / mention_count / skw_status */
export async function updateKeywordSkwBatch(
  rows: { id: string; skw_score: number; mention_count: number; skw_status: string }[],
): Promise<void> {
  if (rows.length === 0) return;
  for (const row of rows) {
    await pool.query(
      `UPDATE info_gap_skw
       SET skw_score = $1, mention_count = $2, skw_status = $3
       WHERE id = $4`,
      [row.skw_score, row.mention_count, row.skw_status, row.id],
    );
  }
}

/** 删除指定窗口内某个关键词的所有 info_gap_skw 记录（大模型幻觉词处理） */
export async function deleteKeywordSkwByKeyword(
  sessionId: string,
  windowStart: Date,
  keyword: string,
): Promise<void> {
  await pool.query(
    `DELETE FROM info_gap_skw
     WHERE session_id = $1
       AND window_start = $2
       AND keyword = $3`,
    [sessionId, toUtcString(windowStart), keyword],
  );
}

// ── ai_push_analysis ──────────────────────────────────────────────────────────

export type AiPushDropReason =
  | 'passed'
  | 'needs_prompt_false'
  | 'anchor_invalid'
  | 'content_empty'
  | 'persist_failed';

/** 写入 ai_push_analysis（每次结构化推送 AI 调用的原始结果，不论是否通过过滤） */
export async function writeAiPushAnalysis(row: {
  id: string;
  session_id: string;
  target_user_id: string;
  state_type: string;
  window_start: Date;
  ai_needs_prompt: boolean;
  ai_anchor: Record<string, string> | null;
  ai_content: string | null;
  ai_analysis: string | null;
  drop_reason: AiPushDropReason;
}): Promise<void> {
  await pool.query(
    `INSERT INTO ai_push_analysis
       (id, session_id, target_user_id, state_type, window_start,
        ai_needs_prompt, ai_anchor, ai_content, ai_analysis, drop_reason, created_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())
     ON CONFLICT (id) DO NOTHING`,
    [
      row.id,
      row.session_id,
      row.target_user_id,
      row.state_type,
      toUtcString(row.window_start),
      row.ai_needs_prompt,
      row.ai_anchor ? JSON.stringify(row.ai_anchor) : null,
      row.ai_content,
      row.ai_analysis,
      row.drop_reason,
    ],
  );
}

/** 写入 window_metrics_batch_reasoning（batch_has_reasoning 完整原始输出） */
export async function writeWindowMetricsBatchReasoning(row: {
  session_id: string;
  window_start: Date;
  members: Array<{
    user_id: string;
    reasoning_status: boolean | null;
    evidence_status: boolean | null;
    reasoning_source: string | null;
    evidence_source: string | null;
  }>;
}): Promise<void> {
  const id = 'wmbr_' + nanoid(12);
  await pool.query(
    `INSERT INTO window_metrics_batch_reasoning
       (id, session_id, window_start, members, created_at)
     VALUES ($1, $2, $3, $4, NOW())`,
    [
      id,
      row.session_id,
      toUtcString(row.window_start),
      JSON.stringify(row.members),
    ],
  );
}

// ── info_gap_recall_analysis ───────────────────────────────────────────────────

/** 写入 info_gap_recall_analysis（每次关键词召回 AI 返回的原始判断，包含 needs_prompt=false 的词） */
export async function writeKeywordRecallAnalysis(row: {
  id: string;
  session_id: string;
  window_start: Date;
  keyword: string;
  needs_prompt: boolean;
  target_user_id: string | null;
  llm_reason: string | null;
}): Promise<void> {
  await pool.query(
    `INSERT INTO info_gap_recall_analysis
       (id, session_id, window_start, keyword, needs_prompt, target_user_id, llm_reason, created_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())
     ON CONFLICT (id) DO NOTHING`,
    [
      row.id,
      row.session_id,
      toUtcString(row.window_start),
      row.keyword,
      row.needs_prompt,
      row.target_user_id,
      row.llm_reason,
    ],
  );
}

/** 批量写入 info_gap_skw */
export async function writeKeywordSkw(rows: KeywordSkwRow[]): Promise<void> {
  if (rows.length === 0) return;

  const values: unknown[] = [];
  const placeholders = rows.map((row, i) => {
    const base = i * 9;
    values.push(
      'skw_' + nanoid(12),
      row.session_id,
      toUtcString(row.window_start),
      row.keyword,
      row.user_a_id ?? null,
      row.user_b_id ?? null,
      row.skw_score ?? null,
      row.mention_count ?? null,
      row.skw_status ?? null,
    );
    return `($${base + 1}, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}, $${base + 7}, $${base + 8}, $${base + 9}, NOW())`;
  });

  await pool.query(
    `INSERT INTO info_gap_skw
       (id, session_id, window_start, keyword, user_a_id, user_b_id, skw_score, mention_count, skw_status, created_at)
     VALUES ${placeholders.join(', ')}
     ON CONFLICT DO NOTHING`,
    values,
  );
}
