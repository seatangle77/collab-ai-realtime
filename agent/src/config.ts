import dotenv from 'dotenv';
import path from 'path';
const env = process.env.NODE_ENV ?? 'local';
// 先加载环境配置，再加载密钥（密钥优先级更高）
dotenv.config({ path: `.env.${env}` });
dotenv.config({ path: path.resolve(__dirname, '../../secrets.env') });

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
    adminToken: requireEnv('ADMIN_API_KEY', ''),
  },
  agent: {
    analysisIntervalMs: parseInt(process.env.ANALYSIS_INTERVAL_MS ?? '60000', 10),
    infoGapIntervalMs: parseInt(process.env.INFO_GAP_INTERVAL_MS ?? '60000', 10),
    infoGapDecisionIntervalMs: parseInt(process.env.INFO_GAP_DECISION_INTERVAL_MS ?? '120000', 10),
    longIntervalMs: parseInt(process.env.LONG_INTERVAL_MS ?? '120000', 10),
    sessionPollMs: parseInt(process.env.SESSION_POLL_MS ?? '15000', 10),
  },
} as const;
