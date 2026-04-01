import dotenv from 'dotenv';
dotenv.config();

function requireEnv(key: string, fallback?: string): string {
  const val = process.env[key] ?? fallback;
  if (val === undefined) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return val;
}

export const config = {
  db: {
    host: process.env.DB_HOST ?? '127.0.0.1',
    port: parseInt(process.env.DB_PORT ?? '5432', 10),
    database: process.env.DB_NAME ?? 'collaborative_ai_chatbot',
    user: requireEnv('DB_USER', 'postgres'),
    password: requireEnv('DB_PASSWORD', ''),
  },
  nlp: {
    baseUrl: process.env.NLP_BASE_URL ?? 'http://localhost:8000',
    adminToken: requireEnv('ADMIN_TOKEN', ''),
  },
  agent: {
    shortIntervalMs: parseInt(process.env.SHORT_INTERVAL_MS ?? '30000', 10),
    longIntervalMs: parseInt(process.env.LONG_INTERVAL_MS ?? '120000', 10),
    sessionPollMs: parseInt(process.env.SESSION_POLL_MS ?? '15000', 10),
  },
} as const;
