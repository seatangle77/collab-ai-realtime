import { getTranscriptsInWindow, getHistoricalWindowMetricsKeywords, writeWindowMetricsKeywords } from '../../db/queries';
import { extractKeywordsBroad, embed, similarity } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:info-gain');

export interface InfoGainResult {
  /** user_id → info_gain (0~1)，无当前发言则为 null */
  infoGains: Record<string, number | null>;
}

// 语义覆盖阈值：历史关键词与当前关键词相似度超过此值视为"已覆盖"
const COVERAGE_THRESHOLD = 0.75;

/**
 * I_gain = |新增语义关键词| / |Kcur|
 *
 * info_gain 独立于 info_gap 流程，自行提取关键词：
 * 1. 查询当前窗口的发言文本
 * 2. 用宽松 TF-IDF（仅去停用词）提取本轮关键词 Kcur
 * 3. 从 window_metrics_keywords 取历史关键词 Khistory
 * 4. 对每个 Kcur 中的词，若与 Khistory 任意词相似度 < COVERAGE_THRESHOLD，视为新词
 * 5. info_gain = 新词数 / |Kcur|
 * 6. 将本轮 Kcur 写入 window_metrics_keywords 供下一窗口使用
 *
 * info_gain 是 session 级别指标，所有成员共享同一个值。
 */
export async function computeInfoGain(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<InfoGainResult> {
  const infoGains: Record<string, number | null> = {};

  // Step 1: 获取当前窗口发言文本
  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);
  const texts = transcripts.map((t) => t.text ?? '').filter(Boolean);

  if (texts.length === 0) {
    logger.info('[信息增益 InfoGain] 当前窗口无发言，跳过', { sessionId });
    for (const uid of memberIds) infoGains[uid] = null;
    return { infoGains };
  }

  // Step 2: 宽松 TF-IDF 提取本轮关键词
  const currentKeywords = await extractKeywordsBroad(texts);
  logger.info(`[信息增益 InfoGain] 本轮宽松关键词（${currentKeywords.length} 个）：${currentKeywords.join('、') || '（无）'}`, { sessionId });

  if (currentKeywords.length === 0) {
    for (const uid of memberIds) infoGains[uid] = null;
    return { infoGains };
  }

  // Step 3: 查历史关键词
  const historicalRows = await getHistoricalWindowMetricsKeywords(sessionId, windowStart);
  const historicalKeywords = historicalRows.map((r) => r.keyword);

  let gain: number;

  if (historicalKeywords.length === 0) {
    // 首窗口无历史，所有词都是新词
    gain = 1.0;
    logger.info(`[信息增益 InfoGain] 首窗口，gain=1.0`, { sessionId });
  } else {
    // Step 4: embed + similarity 计算新词数
    const allTexts = [...currentKeywords, ...historicalKeywords];
    logger.info(`[信息增益 InfoGain] 向量化本轮（${currentKeywords.length}）+ 历史（${historicalKeywords.length}）个关键词`, { sessionId });
    const allEmbeddings = await embed(allTexts);

    const curEmbeddings = allEmbeddings.slice(0, currentKeywords.length);
    const histEmbeddings = allEmbeddings.slice(currentKeywords.length);

    const pairs: Array<{ vec_a: number[]; vec_b: number[] }> = [];
    const pairIndex: Array<{ curIdx: number }> = [];

    for (let ci = 0; ci < curEmbeddings.length; ci++) {
      for (let hi = 0; hi < histEmbeddings.length; hi++) {
        pairs.push({ vec_a: curEmbeddings[ci], vec_b: histEmbeddings[hi] });
        pairIndex.push({ curIdx: ci });
      }
    }

    const scores = await similarity(pairs);

    const maxSimByCur: number[] = new Array(currentKeywords.length).fill(0);
    scores.forEach((score, idx) => {
      const { curIdx } = pairIndex[idx];
      if (score > maxSimByCur[curIdx]) maxSimByCur[curIdx] = score;
    });

    const newWordCount = maxSimByCur.filter((s) => s < COVERAGE_THRESHOLD).length;
    gain = newWordCount / currentKeywords.length;

    const newKeywords = currentKeywords.filter((_, i) => maxSimByCur[i] < COVERAGE_THRESHOLD);
    const level = gain >= 0.6 ? '高（大量新内容）' : gain >= 0.3 ? '中' : '低（内容重复）';
    logger.info(`[信息增益 InfoGain] 结果：gain=${gain.toFixed(3)}（${level}），新词 ${newWordCount}/${currentKeywords.length} 个，新词：${newKeywords.join('、') || '（无）'}`, { sessionId });
  }

  // Step 5: 写入本轮关键词供下一窗口历史对比
  await writeWindowMetricsKeywords(sessionId, windowStart, currentKeywords);

  for (const uid of memberIds) {
    infoGains[uid] = gain;
  }

  return { infoGains };
}
