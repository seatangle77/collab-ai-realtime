import { getHistoricalKeywords } from '../../db/queries';
import { embed, similarity } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:info-gain');

export interface InfoGainResult {
  /** user_id → info_gain (0~1)，无当前关键词则为 null */
  infoGains: Record<string, number | null>;
}

// 语义覆盖阈值：历史关键词与当前关键词相似度超过此值视为"已覆盖"
const COVERAGE_THRESHOLD = 0.75;

/**
 * I_gain = |新增语义关键词| / |Kcur|
 *
 * 对每位用户：
 * 1. 取当前窗口该用户在 keyword_skw 中出现过的关键词作为 Kcur
 * 2. 取历史所有窗口的关键词作为 Khistory
 * 3. 对每个 Kcur 中的词，若与 Khistory 任意词的相似度 < COVERAGE_THRESHOLD，视为新词
 * 4. info_gain = 新词数 / |Kcur|
 *
 * 注意：info_gain 是 session 级别指标（不区分用户），
 * 这里对所有成员统一计算同一个值并复制到每位用户。
 */
export async function computeInfoGain(
  sessionId: string,
  windowStart: Date,
  _windowEnd: Date,
  memberIds: string[],
  currentKeywords: string[],
): Promise<InfoGainResult> {
  const infoGains: Record<string, number | null> = {};

  if (currentKeywords.length === 0) {
    for (const uid of memberIds) infoGains[uid] = null;
    return { infoGains };
  }

  const historicalRows = await getHistoricalKeywords(sessionId, windowStart);
  const historicalKeywords = historicalRows.map((r) => r.keyword);

  // 第一个窗口无历史，所有词都是新词
  if (historicalKeywords.length === 0) {
    for (const uid of memberIds) infoGains[uid] = 1.0;
    return { infoGains };
  }

  // embed 当前关键词 + 历史关键词
  const allTexts = [...currentKeywords, ...historicalKeywords];
  logger.info(`[信息增益 InfoGain] 正在向量化本轮关键词（${currentKeywords.length} 个）+ 历史关键词（${historicalKeywords.length} 个）`, { sessionId });
  const allEmbeddings = await embed(allTexts);

  const curEmbeddings = allEmbeddings.slice(0, currentKeywords.length);
  const histEmbeddings = allEmbeddings.slice(currentKeywords.length);

  // 对每个当前词，判断是否被历史词覆盖
  const pairs: Array<{ vec_a: number[]; vec_b: number[] }> = [];
  const pairIndex: Array<{ curIdx: number; histIdx: number }> = [];

  for (let ci = 0; ci < curEmbeddings.length; ci++) {
    for (let hi = 0; hi < histEmbeddings.length; hi++) {
      pairs.push({ vec_a: curEmbeddings[ci], vec_b: histEmbeddings[hi] });
      pairIndex.push({ curIdx: ci, histIdx: hi });
    }
  }

  const scores = await similarity(pairs);

  // 每个当前词与历史词的最大相似度
  const maxSimByCur: number[] = new Array(currentKeywords.length).fill(0);
  scores.forEach((score, idx) => {
    const { curIdx } = pairIndex[idx];
    if (score > maxSimByCur[curIdx]) maxSimByCur[curIdx] = score;
  });

  const newWordCount = maxSimByCur.filter((s) => s < COVERAGE_THRESHOLD).length;
  const gain = newWordCount / currentKeywords.length;

  const newKeywords = currentKeywords.filter((_, i) => maxSimByCur[i] < COVERAGE_THRESHOLD);
  const level = gain >= 0.6 ? '高（大量新内容）' : gain >= 0.3 ? '中' : '低（内容重复）';
  logger.info(`[信息增益 InfoGain] 结果：gain=${gain.toFixed(3)}（${level}），新词 ${newWordCount}/${currentKeywords.length} 个，新词：${newKeywords.join('、') || '（无）'}`, { sessionId });

  for (const uid of memberIds) {
    infoGains[uid] = gain;
  }

  return { infoGains };
}
