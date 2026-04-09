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
}

export interface KeywordSkwRow {
  session_id: string;
  window_start: Date;
  keyword: string;
  user_a_id: string;
  user_b_id: string;
  skw_score: number;
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
  status: 'pending' | 'delivered' | 'skipped' | 'failed';
  created_at: Date;
  delivered_at: Date | null;
}

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
     WHERE status = 'ongoing'`,
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
       AND t."end" <= $3
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

/** 获取历史窗口中的关键词（用于 info_gain 计算） */
export async function getHistoricalKeywords(
  sessionId: string,
  before: Date,
): Promise<HistoricalKeyword[]> {
  const res = await pool.query<HistoricalKeyword>(
    `SELECT DISTINCT keyword
     FROM keyword_skw
     WHERE session_id = $1
       AND window_start < $2`,
    [sessionId, toUtcString(before)],
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
        srep, info_gain, has_reasoning, has_evidence, created_at)
     VALUES
       ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())`,
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

/** 写入 push_logs */
export async function writePushLog(row: {
  session_id: string;
  state_id: string;
  target_user_id: string;
  push_content: string;
  content_embedding: number[];
  push_channel: 'glasses' | 'app';
  delivery_status?: 'pending' | 'delivered' | 'failed';
  delivered_at?: Date;
}): Promise<void> {
  const id = 'pl_' + nanoid(12);
  await pool.query(
    `INSERT INTO push_logs
       (id, session_id, state_id, target_user_id,
        push_content, content_embedding, push_channel, delivery_status, triggered_at, delivered_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)`,
    [
      id,
      row.session_id,
      row.state_id,
      row.target_user_id,
      row.push_content,
      row.content_embedding,
      row.push_channel,
      row.delivery_status ?? 'pending',
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
       AND status = 'pending'
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
       AND pl.push_channel = 'glasses'
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
  status: 'delivered' | 'skipped' | 'failed',
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
}): Promise<string | null> {
  const id = 'igb_' + nanoid(12);
  const res = await pool.query<{ id: string }>(
    `INSERT INTO info_gap_buttons
       (id, session_id, user_id, keyword, skw_score, window_start, status, created_at)
     VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
     ON CONFLICT DO NOTHING
     RETURNING id`,
    [id, row.session_id, row.user_id, row.keyword, row.skw_score, toUtcString(row.window_start)],
  );
  return res.rows[0]?.id ?? null;
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

/** 写入讨论摘要 */
export async function writeDiscussionSummary(row: {
  session_id: string;
  summary_text: string;
  window_start: Date;
  window_end: Date;
}): Promise<void> {
  const id = 'sum_' + nanoid(12);
  await pool.query(
    `INSERT INTO discussion_summaries
       (id, session_id, summary_text, window_start, window_end, created_at)
     VALUES ($1, $2, $3, $4, $5, NOW())`,
    [id, row.session_id, row.summary_text, toUtcString(row.window_start), toUtcString(row.window_end)],
  );
}

/** 批量写入 keyword_skw */
export async function writeKeywordSkw(rows: KeywordSkwRow[]): Promise<void> {
  if (rows.length === 0) return;

  const values: unknown[] = [];
  const placeholders = rows.map((row, i) => {
    const base = i * 7;
    values.push(
      'skw_' + nanoid(12),
      row.session_id,
      toUtcString(row.window_start),
      row.keyword,
      row.user_a_id,
      row.user_b_id,
      row.skw_score,
    );
    return `($${base + 1}, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}, $${base + 7}, NOW())`;
  });

  await pool.query(
    `INSERT INTO keyword_skw
       (id, session_id, window_start, keyword, user_a_id, user_b_id, skw_score, created_at)
     VALUES ${placeholders.join(', ')}`,
    values,
  );
}
