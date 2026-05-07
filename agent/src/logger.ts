type Level = 'info' | 'warn' | 'error' | 'debug';

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
}

export function createLogger(context: string) {
  return {
    info:  (msg: string, meta?: unknown) => log('info',  context, msg, meta),
    warn:  (msg: string, meta?: unknown) => log('warn',  context, msg, meta),
    error: (msg: string, meta?: unknown) => log('error', context, msg, meta),
    debug: (msg: string, meta?: unknown) => log('debug', context, msg, meta),
  };
}
