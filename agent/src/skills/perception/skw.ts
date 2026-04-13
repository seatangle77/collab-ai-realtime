import { getTranscriptsInWindow, writeKeywordSkw, KeywordSkwRow } from '../../db/queries';
import { tfidf, embed, similarity } from '../../http/nlp-client';
import { createLogger } from '../../logger';

const logger = createLogger('skill:skw');

export interface SkwResult {
  /**
   * 全局关键词列表（来自 tfidf）
   * keyword_skw 表已同步写入
   */
  keywords: string[];
  /**
   * keyword → { userA_id → { userB_id → skw_score } }
   * 用于后续 info_gain 消费
   */
  scores: Record<string, Record<string, Record<string, number>>>;
}

/**
 * Skw：关键词跨成员语义相似度
 *
 * 步骤：
 * 1. 用 /tfidf 提取全局 top-N 关键词 + 每位成员的上下文句子
 * 2. 对每个关键词，取每位成员的上下文句子做 embed
 * 3. 对所有成员 pair (a, b) 计算余弦相似度 → skw_score
 * 4. 写入 keyword_skw 表
 */
export async function computeSkw(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<SkwResult> {
  if (memberIds.length < 2) {
    return { keywords: [], scores: {} };
  }

  const transcripts = await getTranscriptsInWindow(sessionId, windowStart, windowEnd);

  // 聚合每位成员的发言文本
  const textByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textByUser[uid] = [];
  for (const t of transcripts) {
    if (t.user_id && t.text && t.user_id in textByUser) textByUser[t.user_id].push(t.text);
  }

  // 过滤掉无发言成员
  const activeMemberTexts: Record<string, string> = {};
  for (const uid of memberIds) {
    const combined = textByUser[uid].join(' ').trim();
    if (combined) activeMemberTexts[uid] = combined;
  }

  if (Object.keys(activeMemberTexts).length < 2) {
    return { keywords: [], scores: {} };
  }

  logger.info(`[关键词提取 TF-IDF] 正在提取 ${Object.keys(activeMemberTexts).length} 位活跃成员的关键词`, { sessionId });
  const tfidfResult = await tfidf(activeMemberTexts, 5);
  const { keywords, member_keyword_contexts } = tfidfResult;
  logger.info(`[关键词提取 TF-IDF] 提取完成，关键词：${keywords.join('、') || '（无）'}`, { sessionId });

  if (keywords.length === 0) {
    return { keywords: [], scores: {} };
  }

  const activeMembers = Object.keys(activeMemberTexts);
  const skwRows: KeywordSkwRow[] = [];
  const scores: SkwResult['scores'] = {};

  for (const keyword of keywords) {
    scores[keyword] = {};

    // 只保留实际提及该关键词的成员（无上下文则跳过，避免全文回退导致误报）
    const contextByUser: Record<string, string> = {};
    for (const uid of activeMembers) {
      const ctx = member_keyword_contexts[uid]?.[keyword];
      if (ctx) contextByUser[uid] = ctx;
    }

    // 少于 2 位成员提及该关键词，跳过（无法形成有意义的语义差异）
    if (Object.keys(contextByUser).length < 2) {
      logger.info(`[跨成员语义相似度 Skw] 关键词「${keyword}」：提及人数不足 2，跳过`, { sessionId });
      continue;
    }

    // 批量 embed（只处理有上下文的成员）
    const keywordMembers = Object.keys(contextByUser);
    const texts = keywordMembers.map((uid) => contextByUser[uid]);
    logger.info(`[跨成员语义相似度 Skw] 关键词「${keyword}」：向量化 ${texts.length} 位成员的上下文`, { sessionId });
    const embeddings = await embed(texts);
    const embeddingByUser: Record<string, number[]> = {};
    keywordMembers.forEach((uid, i) => {
      embeddingByUser[uid] = embeddings[i];
    });

    // 所有 pair (a, b) 计算相似度
    const pairs: Array<{ vec_a: number[]; vec_b: number[] }> = [];
    const pairMeta: Array<{ userA: string; userB: string }> = [];

    for (let i = 0; i < keywordMembers.length; i++) {
      for (let j = i + 1; j < keywordMembers.length; j++) {
        const userA = keywordMembers[i];
        const userB = keywordMembers[j];
        pairs.push({ vec_a: embeddingByUser[userA], vec_b: embeddingByUser[userB] });
        pairMeta.push({ userA, userB });
      }
    }

    const simScores = await similarity(pairs);

    simScores.forEach((score, idx) => {
      const { userA, userB } = pairMeta[idx];
      const level = score >= 0.85 ? '高度一致' : score >= 0.6 ? '部分重叠' : '差异显著';
      logger.info(`[跨成员语义相似度 Skw] 关键词「${keyword}」${userA} vs ${userB}：相似度=${score.toFixed(3)}（${level}）`, { sessionId });

      if (!scores[keyword][userA]) scores[keyword][userA] = {};
      if (!scores[keyword][userB]) scores[keyword][userB] = {};
      scores[keyword][userA][userB] = score;
      scores[keyword][userB][userA] = score;

      skwRows.push({
        session_id: sessionId,
        window_start: windowStart,
        keyword,
        user_a_id: userA,
        user_b_id: userB,
        skw_score: score,
      });
    });
  }

  await writeKeywordSkw(skwRows);

  return { keywords, scores };
}
