import {
  getTranscriptsInWindow,
  writeKeywordSkw,
  updateKeywordSkwBatch,
  deleteKeywordSkwByKeyword,
  writeInfoGapButton,
  hasPendingInfoGapKeyword,
  hasClickedInfoGapKeywordInRecentWindows,
} from '../../db/queries';
import { keywordRecallWithGap, embed, similarity, notifyInfoGapButton } from '../../http/nlp-client';
import { createLogger } from '../../logger';
import { nanoid } from 'nanoid';

const logger = createLogger('skill:skw');

const WINDOW_MS = 2 * 60 * 1000;
const RECENT_WINDOW_COUNT = 3;

export interface SkwResult {
  keywords: string[];
  scores: Record<string, Record<string, Record<string, number>>>;
}

function splitSentences(text: string): string[] {
  return text
    .split(/[。！？.!?\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function findContext(text: string, keyword: string): string {
  const hit = splitSentences(text).find((s) => s.includes(keyword));
  return hit ?? '';
}

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

  const textByUser: Record<string, string[]> = {};
  for (const uid of memberIds) textByUser[uid] = [];
  for (const t of transcripts) {
    if (t.user_id && t.text && t.user_id in textByUser) textByUser[t.user_id].push(t.text);
  }

  const activeMemberTexts: Record<string, string> = {};
  for (const uid of memberIds) {
    const combined = textByUser[uid].join(' ').trim();
    if (combined) activeMemberTexts[uid] = combined;
  }

  if (Object.keys(activeMemberTexts).length < 2) {
    return { keywords: [], scores: {} };
  }

  // ── 阶段一：大模型召回 + 评估 ────────────────────────────────────────────────

  logger.info('[SKW] 调用大模型召回关键词', { sessionId });
  const recallResult = await keywordRecallWithGap(activeMemberTexts);
  const recallKeywords = recallResult.keywords ?? [];

  if (recallKeywords.length === 0) {
    logger.info('[SKW] 大模型未返回关键词，终止', { sessionId });
    return { keywords: [], scores: {} };
  }

  // needs_prompt 信息暂存内存：word -> { needs_prompt, target_user_id, reason }
  const needsPromptMap: Record<string, { needs_prompt: boolean; target_user_id: string; reason: string }> = {};
  for (const item of recallKeywords) {
    needsPromptMap[item.word] = {
      needs_prompt: item.needs_prompt,
      target_user_id: item.target_user_id,
      reason: item.reason,
    };
  }

  const words = recallKeywords.map((k) => k.word);
  logger.info(`[SKW] 召回关键词：${words.join('、')}`, { sessionId });

  // ── 阶段二：写入 keyword_skw 初始记录（pending）────────────────────────────

  const activeMembers = Object.keys(activeMemberTexts);

  // 生成所有 pair 组合，并记录每条记录的 id 供后续更新
  // pendingIds: word -> [{ id, userA, userB }]
  const pendingIds: Record<string, { id: string; userA: string; userB: string }[]> = {};

  const initialRows = [];
  for (const word of words) {
    pendingIds[word] = [];
    for (let i = 0; i < activeMembers.length; i++) {
      for (let j = i + 1; j < activeMembers.length; j++) {
        const id = 'skw_' + nanoid(12);
        pendingIds[word].push({ id, userA: activeMembers[i], userB: activeMembers[j] });
        initialRows.push({
          id,
          session_id: sessionId,
          window_start: windowStart,
          keyword: word,
          user_a_id: activeMembers[i],
          user_b_id: activeMembers[j],
          skw_score: undefined,
          mention_count: undefined,
          skw_status: 'pending',
        });
      }
    }
  }

  await writeKeywordSkw(initialRows);
  logger.info(`[SKW] 写入初始记录 ${initialRows.length} 条`, { sessionId });

  // ── 阶段三：SKW 分数计算，更新 keyword_skw ──────────────────────────────────

  const scores: SkwResult['scores'] = {};
  // 记录每个词每个 user 最终的 skw_score（用于阶段四查分）
  const skwScoreByWordUser: Record<string, Record<string, number>> = {};

  for (const word of words) {
    scores[word] = {};
    skwScoreByWordUser[word] = {};

    // 找到实际提及该词的成员及其上下文句子
    const contextByUser: Record<string, string> = {};
    for (const uid of activeMembers) {
      const ctx = findContext(activeMemberTexts[uid], word);
      if (ctx) contextByUser[uid] = ctx;
    }

    const mentionCount = Object.keys(contextByUser).length;
    const pairs = pendingIds[word];

    // 0人提及：大模型幻觉，删除初始记录
    if (mentionCount === 0) {
      logger.info(`[SKW] 关键词「${word}」无人提及（幻觉），删除记录`, { sessionId });
      await deleteKeywordSkwByKeyword(sessionId, windowStart, word);
      delete needsPromptMap[word];
      continue;
    }

    const updateRows: { id: string; skw_score: number; mention_count: number; skw_status: string }[] = [];

    if (mentionCount === 1) {
      // 1人提及：全部更新为 single_mention
      logger.info(`[SKW] 关键词「${word}」仅1人提及`, { sessionId });
      const mentioner = Object.keys(contextByUser)[0];
      for (const { id, userA, userB } of pairs) {
        updateRows.push({ id, skw_score: 0.1, mention_count: 1, skw_status: 'single_mention' });
        scores[word][userA] = scores[word][userA] ?? {};
        scores[word][userB] = scores[word][userB] ?? {};
        scores[word][userA][userB] = 0.1;
        scores[word][userB][userA] = 0.1;
      }
      skwScoreByWordUser[word][mentioner] = 0.1;

    } else {
      // 2人或3人提及：对有上下文的成员做 embedding，计算余弦相似度
      const mentioners = Object.keys(contextByUser);
      const texts = mentioners.map((uid) => contextByUser[uid]);
      logger.info(`[SKW] 关键词「${word}」${mentionCount}人提及，开始 embedding`, { sessionId });

      const embeddings = await embed(texts);
      const embeddingByUser: Record<string, number[]> = {};
      mentioners.forEach((uid, i) => { embeddingByUser[uid] = embeddings[i]; });

      // 计算所有提及者之间的相似度
      const simPairs: { vec_a: number[]; vec_b: number[] }[] = [];
      const simMeta: { userA: string; userB: string }[] = [];
      for (let i = 0; i < mentioners.length; i++) {
        for (let j = i + 1; j < mentioners.length; j++) {
          simPairs.push({ vec_a: embeddingByUser[mentioners[i]], vec_b: embeddingByUser[mentioners[j]] });
          simMeta.push({ userA: mentioners[i], userB: mentioners[j] });
        }
      }

      const simScores = await similarity(simPairs);
      const simMap: Record<string, Record<string, number>> = {};
      simScores.forEach((score, idx) => {
        const { userA, userB } = simMeta[idx];
        simMap[userA] = simMap[userA] ?? {};
        simMap[userB] = simMap[userB] ?? {};
        simMap[userA][userB] = score;
        simMap[userB][userA] = score;
        scores[word][userA] = scores[word][userA] ?? {};
        scores[word][userB] = scores[word][userB] ?? {};
        scores[word][userA][userB] = score;
        scores[word][userB][userA] = score;
        logger.info(`[SKW] 「${word}」${userA} vs ${userB} 相似度=${score.toFixed(3)}`, { sessionId });
      });

      // 按 pair 记录更新值
      for (const { id, userA, userB } of pairs) {
        const bothMentioned = userA in contextByUser && userB in contextByUser;
        if (bothMentioned) {
          const score = simMap[userA]?.[userB] ?? 0.1;
          updateRows.push({ id, skw_score: score, mention_count: mentionCount, skw_status: 'computed' });
        } else {
          updateRows.push({ id, skw_score: 0.1, mention_count: mentionCount, skw_status: 'single_mention' });
          scores[word][userA] = scores[word][userA] ?? {};
          scores[word][userB] = scores[word][userB] ?? {};
          scores[word][userA][userB] = 0.1;
          scores[word][userB][userA] = 0.1;
        }
      }

      for (const uid of mentioners) {
        // 取该用户与其他所有人的平均分作为代表分
        const peerScores = Object.values(simMap[uid] ?? {});
        skwScoreByWordUser[word][uid] = peerScores.length > 0
          ? peerScores.reduce((a, b) => a + b, 0) / peerScores.length
          : 0.1;
      }
    }

    await updateKeywordSkwBatch(updateRows);
  }

  // ── 阶段四：写入 info_gap_buttons，推送按钮 ──────────────────────────────────

  for (const word of Object.keys(needsPromptMap)) {
    const { needs_prompt, target_user_id, reason } = needsPromptMap[word];
    if (!needs_prompt || !target_user_id) continue;

    // 去重：已有 pending 按钮则跳过
    const alreadyPending = await hasPendingInfoGapKeyword(sessionId, target_user_id, word);
    if (alreadyPending) {
      logger.info(`[SKW] 「${word}」用户 ${target_user_id} 已有 pending 按钮，跳过`, { sessionId });
      continue;
    }

    // 近期已点击过则跳过
    const recentlyClicked = await hasClickedInfoGapKeywordInRecentWindows(
      sessionId, target_user_id, word, windowStart, RECENT_WINDOW_COUNT, WINDOW_MS,
    );
    if (recentlyClicked) {
      logger.info(`[SKW] 「${word}」用户 ${target_user_id} 近期已点击，跳过`, { sessionId });
      continue;
    }

    const skwScore = skwScoreByWordUser[word]?.[target_user_id] ?? 0.1;

    const buttonId = await writeInfoGapButton({
      session_id: sessionId,
      user_id: target_user_id,
      keyword: word,
      skw_score: skwScore,
      window_start: windowStart,
      llm_reason: reason,
    });

    if (!buttonId) {
      logger.info(`[SKW] 「${word}」writeInfoGapButton 未插入（ON CONFLICT），跳过`, { sessionId });
      continue;
    }

    await notifyInfoGapButton({
      session_id: sessionId,
      user_id: target_user_id,
      button_id: buttonId,
      keyword: word,
      skw_score: skwScore,
      window_start: windowStart.toISOString(),
    });

    logger.info(`[SKW] 「${word}」按钮已推送给用户 ${target_user_id}`, { sessionId });
  }

  return { keywords: words, scores };
}
