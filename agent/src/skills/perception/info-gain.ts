import { getTranscriptsInWindow, getHistoricalWindowMetricsKeywords, writeWindowMetricsKeywords } from '../../db/queries';
import { extractKeywordsBroad, embed, similarity } from '../../http/nlp-client';
import { createLogger } from '../../logger';
import { config } from '../../config';

const logger = createLogger('skill:info-gain');

export interface InfoGainResult {
  /** user_id → info_gain (0~1)，无当前发言则为 null */
  infoGains: Record<string, number | null>;
}

// 语义覆盖阈值：历史关键词与当前关键词相似度超过此值视为"已覆盖"
const COVERAGE_THRESHOLD = 0.75;

/**
 * I_gain_i = |新增语义关键词_i| / |Kcur_i|
 *
 * 按成员分别计算，每人只用自己的发言文本：
 * 1. 查询当前窗口各成员发言文本
 * 2. 每人各自用宽松 TF-IDF 提取本轮关键词 Kcur_i
 * 3. 从 window_metrics_keywords 取该成员最近2个窗口的历史关键词 Khistory_i
 * 4. 对每个 Kcur_i 中的词，若与 Khistory_i 任意词相似度 < COVERAGE_THRESHOLD，视为新词
 * 5. info_gain_i = 新词数 / |Kcur_i|
 * 6. 将本轮 Kcur_i 写入 window_metrics_keywords 供下一窗口使用
 *
 * 首窗口（无历史）返回 null，不触发停滞判断。
 */
export async function computeInfoGain(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<InfoGainResult> {
  const infoGains: Record<string, number | null> = {};

  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  // 按成员分组发言文本
  const textsByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textsByUser[uid] = [];
  for (const t of transcripts) {
    if (t.user_id && t.text && t.user_id in textsByUser) {
      textsByUser[t.user_id].push(t.text);
    }
  }

  // 历史窗口起点：往前推2个窗口
  const historyStart = new Date(windowStart.getTime() - 2 * config.agent.longIntervalMs);

  await Promise.allSettled(
    memberIds.map(async (uid) => {
      const texts = textsByUser[uid].filter(Boolean);

      if (texts.length === 0) {
        logger.info(`[信息增益 InfoGain] 用户 ${uid} 本窗口无发言，跳过`, { sessionId });
        infoGains[uid] = null;
        return;
      }

      // Step 1: 提取本人本轮关键词
      const currentKeywords = await extractKeywordsBroad(texts);
      logger.info(`[信息增益 InfoGain] 用户 ${uid} 本轮关键词（${currentKeywords.length} 个）：${currentKeywords.join('、') || '（无）'}`, { sessionId });

      if (currentKeywords.length === 0) {
        infoGains[uid] = null;
        return;
      }

      // Step 2: 查该成员最近2个窗口的历史关键词
      const historicalRows = await getHistoricalWindowMetricsKeywords(sessionId, uid, windowStart, historyStart);
      const historicalKeywords = historicalRows.map((r) => r.keyword);

      if (historicalKeywords.length === 0) {
        // 首窗口无历史，返回 null
        logger.info(`[信息增益 InfoGain] 用户 ${uid} 首窗口无历史，跳过计算`, { sessionId });
        await writeWindowMetricsKeywords(sessionId, uid, windowStart, currentKeywords);
        infoGains[uid] = null;
        return;
      }

      // Step 3: embed + similarity 计算新词数
      const allTexts = [...currentKeywords, ...historicalKeywords];
      logger.info(`[信息增益 InfoGain] 用户 ${uid} 向量化本轮（${currentKeywords.length}）+ 历史（${historicalKeywords.length}）个关键词`, { sessionId });
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
      const gain = newWordCount / currentKeywords.length;

      const newKeywords = currentKeywords.filter((_, i) => maxSimByCur[i] < COVERAGE_THRESHOLD);
      const level = gain >= 0.6 ? '高（大量新内容）' : gain >= 0.3 ? '中' : '低（内容重复）';
      logger.info(`[信息增益 InfoGain] 用户 ${uid} 结果：gain=${gain.toFixed(3)}（${level}），新词 ${newWordCount}/${currentKeywords.length} 个，新词：${newKeywords.join('、') || '（无）'}`, { sessionId });

      // Step 4: 写入本轮关键词
      await writeWindowMetricsKeywords(sessionId, uid, windowStart, currentKeywords);
      infoGains[uid] = gain;
    }),
  );

  // 确保所有成员都有值
  for (const uid of memberIds) {
    if (!(uid in infoGains)) infoGains[uid] = null;
  }

  return { infoGains };
}
