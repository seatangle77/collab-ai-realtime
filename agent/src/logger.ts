type Level = 'info' | 'warn' | 'error' | 'debug';

function log(level: Level, context: string, message: string, meta?: unknown): void {
  const ts = new Date().toISOString();
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
