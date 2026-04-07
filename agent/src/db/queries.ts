import { pool } from './client';
import { nanoid } from 'nanoid';

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
    `SELECT transcript_id,
            COALESCE(NULLIF(user_id, ''), NULLIF(speaker, ''), NULLIF(speaker, 'unknown')) AS user_id,
            text, start, "end", duration
     FROM speech_transcripts
     WHERE session_id = $1
       AND start >= $2
       AND "end" <= $3
       AND text IS NOT NULL
       AND text != ''
     ORDER BY start ASC`,
    [sessionId, toUtcString(windowStart), toUtcString(windowEnd)],
  );
  return res.rows;
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

/** 获取 session 全局最近发言 end（群体沉默检测用） */
export async function getLastSpeakEndGlobal(
  sessionId: string,
): Promise<Date | null> {
  const res = await pool.query<{ last_end: Date | null }>(
    `SELECT MAX("end") AS last_end
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
  push_cooldown_until: Date;
}): Promise<string> {
  const id = 'ds_' + nanoid(12);
  await pool.query(
    `INSERT INTO discussion_states
       (id, session_id, state_type, target_user_id, trigger_metrics,
        window_start, push_cooldown_until, triggered_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())`,
    [
      id,
      row.session_id,
      row.state_type,
      row.target_user_id ?? null,
      JSON.stringify(row.trigger_metrics),
      toUtcString(row.window_start),
      toUtcString(row.push_cooldown_until),
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
  push_channel: 'glasses' | 'app';
}): Promise<void> {
  const id = 'pl_' + nanoid(12);
  await pool.query(
    `INSERT INTO push_logs
       (id, session_id, state_id, target_user_id,
        push_content, push_channel, delivery_status, triggered_at)
     VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())`,
    [id, row.session_id, row.state_id, row.target_user_id, row.push_content, row.push_channel],
  );
}

/** 跨状态冷却：查询某用户最近一次收到推送的时间 */
export async function getLastPushTimeForUser(
  sessionId: string,
  userId: string,
): Promise<Date | null> {
  const res = await pool.query<{ last_push: Date | null }>(
    `SELECT MAX(triggered_at) AS last_push
     FROM push_logs
     WHERE session_id = $1 AND target_user_id = $2`,
    [sessionId, userId],
  );
  return res.rows[0]?.last_push ?? null;
}

/** 单状态冷却：查询某 state_type 对某用户的冷却截止时间 */
export async function getStateCooldownUntil(
  sessionId: string,
  stateType: string,
  userId?: string,
): Promise<Date | null> {
  const res = await pool.query<{ cooldown_until: Date | null }>(
    `SELECT MAX(push_cooldown_until) AS cooldown_until
     FROM discussion_states
     WHERE session_id = $1
       AND state_type = $2
       AND ($3::text IS NULL OR target_user_id = $3)`,
    [sessionId, stateType, userId ?? null],
  );
  return res.rows[0]?.cooldown_until ?? null;
}

/** 写入 info_gap_buttons（静默按钮，等待用户点击） */
export async function writeInfoGapButton(row: {
  session_id: string;
  user_id: string;
  keyword: string;
  skw_score: number;
  window_start: Date;
}): Promise<void> {
  const id = 'igb_' + nanoid(12);
  await pool.query(
    `INSERT INTO info_gap_buttons
       (id, session_id, user_id, keyword, skw_score, window_start, status, created_at)
     VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
     ON CONFLICT DO NOTHING`,
    [id, row.session_id, row.user_id, row.keyword, row.skw_score, toUtcString(row.window_start)],
  );
}

/** 读取最近一条摘要 */
export async function getLastSummary(
  sessionId: string,
): Promise<{ summary_text: string; window_end: Date } | null> {
  const res = await pool.query<{ summary_text: string; window_end: Date }>(
    `SELECT summary_text, window_end
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
