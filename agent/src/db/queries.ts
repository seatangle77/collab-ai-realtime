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
