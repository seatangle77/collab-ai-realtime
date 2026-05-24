import fs from 'fs';
import path from 'path';

type Level = 'info' | 'warn' | 'error' | 'debug';

const SESSION_LOG_DIR = process.env.SESSION_LOG_DIR
  || path.resolve(__dirname, '..', '..', 'logs', 'sessions');

const SHANGHAI_TIME_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

export function formatLogTimestamp(date = new Date()): string {
  const parts = Object.fromEntries(
    SHANGHAI_TIME_FORMATTER.formatToParts(date).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} +08`;
}

function log(level: Level, context: string, message: string, meta?: unknown): void {
  const ts = formatLogTimestamp();
  const prefix = `[${ts}] [${level.toUpperCase().padEnd(5)}] [${context}]`;
  const line = meta !== undefined
    ? `${prefix} ${message} ${JSON.stringify(meta)}`
    : `${prefix} ${message}`;

  if (level === 'error') {
    console.error(line);
  } else if (level === 'warn') {
    console.warn(line);
  } else {
    console.log(line);
  }
  writeSessionLog(line, message, meta);
}

function safeSessionId(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') return null;
  return value.trim().replace(/[^A-Za-z0-9_.:-]/g, '_');
}

function extractSessionId(message: string, meta?: unknown): string | null {
  if (meta && typeof meta === 'object') {
    const record = meta as Record<string, unknown>;
    const fromMeta = safeSessionId(record.sessionId) || safeSessionId(record.session_id);
    if (fromMeta) return fromMeta;
  }

  const match = message.match(/\bsession(?:_id|Id)?=([A-Za-z0-9_.:-]+)/);
  return match ? safeSessionId(match[1]) : null;
}

function writeSessionLog(line: string, message: string, meta?: unknown): void {
  const sessionId = extractSessionId(message, meta);
  if (!sessionId) return;

  try {
    const sessionDir = path.join(SESSION_LOG_DIR, sessionId);
    fs.mkdirSync(sessionDir, { recursive: true });
    fs.appendFileSync(path.join(sessionDir, 'agent.log'), `${line}\n`, 'utf8');
  } catch {
    // Logging must never break the agent's main work.
  }
}

export function createLogger(context: string) {
  return {
    info:  (msg: string, meta?: unknown) => log('info',  context, msg, meta),
    warn:  (msg: string, meta?: unknown) => log('warn',  context, msg, meta),
    error: (msg: string, meta?: unknown) => log('error', context, msg, meta),
    debug: (msg: string, meta?: unknown) => log('debug', context, msg, meta),
  };
}
