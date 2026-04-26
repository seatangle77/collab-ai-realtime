import {
  getTranscriptsInWindow,
  writeKeywordSkw,
  updateKeywordSkwBatch,
  deleteKeywordSkwByKeyword,
  writeInfoGapButton,
  writeKeywordRecallAnalysis,
  hasPendingInfoGapKeyword,
  hasClickedInfoGapKeywordInRecentWindows,
  dismissPendingInfoGapButtonsBeforeWindow,
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

export interface InfoGapKeywordCandidate {
  word: string;
  needs_prompt: boolean;
  target_user_id: string;
  reason: string;
  sourceByUser: Record<string, string>;
  activeMemberIds: string[];
  windowStart: Date;
  windowEnd: Date;
}

export interface InfoGapKeywordRecallResult {
  candidates: InfoGapKeywordCandidate[];
  activeMemberTexts: Record<string, string>;
}

export interface InfoGapDecisionInput {
  sessionId: string;
  windowStart: Date;
  memberIds: string[];
  candidates: InfoGapKeywordCandidate[];
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

async function buildActiveMemberTexts(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<Record<string, string>> {
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
  return activeMemberTexts;
}

function mergeCandidates(candidates: InfoGapKeywordCandidate[]): InfoGapKeywordCandidate[] {
  const byWord = new Map<string, InfoGapKeywordCandidate>();

  for (const item of candidates) {
    const existing = byWord.get(item.word);
    if (!existing) {
      byWord.set(item.word, { ...item, sourceByUser: { ...item.sourceByUser } });
      continue;
    }

    for (const [uid, source] of Object.entries(item.sourceByUser)) {
      if (source) existing.sourceByUser[uid] = existing.sourceByUser[uid] ?? source;
    }

    if (!existing.needs_prompt && item.needs_prompt) {
      existing.needs_prompt = true;
      existing.target_user_id = item.target_user_id;
      existing.reason = item.reason;
    }
    existing.windowEnd = item.windowEnd > existing.windowEnd ? item.windowEnd : existing.windowEnd;
  }

  return [...byWord.values()];
}

export async function recallInfoGapKeywords(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<InfoGapKeywordRecallResult> {
  if (memberIds.length < 2) {
    return { candidates: [], activeMemberTexts: {} };
  }

  const activeMemberTexts = await buildActiveMemberTexts(sessionId, windowStart, windowEnd, memberIds);
  if (Object.keys(activeMemberTexts).length < 2) {
    return { candidates: [], activeMemberTexts };
  }

  logger.info('[SKW] 调用大模型召回关键词', { sessionId });
  const recallResult = await keywordRecallWithGap(activeMemberTexts);
  const recallKeywords = recallResult.keywords ?? [];

  if (recallKeywords.length === 0) {
    logger.info('[SKW] 大模型未返回关键词，终止', { sessionId });
    return { candidates: [], activeMemberTexts };
  }

  const words = recallKeywords.map((k) => k.word);
  logger.info(`[SKW] 召回关键词：${words.join('、')}`, { sessionId });

  await Promise.allSettled(
    recallKeywords.map((item) =>
      Promise.resolve(
        writeKeywordRecallAnalysis({
          id: 'kra_' + nanoid(12),
          session_id: sessionId,
          window_start: windowStart,
          keyword: item.word,
          needs_prompt: item.needs_prompt,
          target_user_id: item.target_user_id || null,
          llm_reason: item.reason || null,
        }),
      ).catch((err: Error) => {
        logger.error('[SKW] writeKeywordRecallAnalysis 失败', {
          sessionId,
          keyword: item.word,
          message: err.message,
        });
      }),
    ),
  );

  const candidates = recallKeywords.map((item): InfoGapKeywordCandidate => {
    const sourceByUser: Record<string, string> = {};
    for (const [uid, text] of Object.entries(activeMemberTexts)) {
      const source = findContext(text, item.word);
      if (source) sourceByUser[uid] = source;
    }

    return {
      word: item.word,
      needs_prompt: item.needs_prompt,
      target_user_id: item.target_user_id,
      reason: item.reason,
      sourceByUser,
      activeMemberIds: Object.keys(activeMemberTexts),
      windowStart,
      windowEnd,
    };
  });

  return { candidates, activeMemberTexts };
}

export async function decideInfoGapButtons(input: InfoGapDecisionInput): Promise<SkwResult> {
  const { sessionId, windowStart, memberIds } = input;
  const candidates = mergeCandidates(input.candidates);
  const words = candidates.map((item) => item.word);

  try {
    const dismissed = await dismissPendingInfoGapButtonsBeforeWindow(sessionId, windowStart);
    if (dismissed > 0) {
      logger.info(`[SKW] 已过期历史 info_gap 按钮 数量=${dismissed}`, { sessionId });
    }
  } catch (err) {
    logger.warn('[SKW] info_gap 按钮过期处理失败', {
      sessionId,
      message: (err as Error).message,
    });
  }

  if (memberIds.length < 2 || candidates.length === 0) {
    return { keywords: words, scores: {} };
  }

  const activeMembers = memberIds.filter((uid) =>
    candidates.some((item) => item.activeMemberIds.includes(uid)),
  );
  if (activeMembers.length < 2) {
    return { keywords: words, scores: {} };
  }

  const candidateByWord = new Map(candidates.map((item) => [item.word, item]));
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

  const scores: SkwResult['scores'] = {};
  const skwScoreByWordUser: Record<string, Record<string, number>> = {};

  for (const word of words) {
    const candidate = candidateByWord.get(word);
    const contextByUser = candidate?.sourceByUser ?? {};
    scores[word] = {};
    skwScoreByWordUser[word] = {};

    const mentionCount = Object.keys(contextByUser).length;
    const pairs = pendingIds[word];

    if (mentionCount === 0) {
      logger.info(`[SKW] 关键词「${word}」无人提及（幻觉），删除记录`, { sessionId });
      await deleteKeywordSkwByKeyword(sessionId, windowStart, word);
      continue;
    }

    const updateRows: { id: string; skw_score: number; mention_count: number; skw_status: string }[] = [];

    if (mentionCount === 1) {
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
      const mentioners = Object.keys(contextByUser);
      const texts = mentioners.map((uid) => contextByUser[uid]);
      logger.info(`[SKW] 关键词「${word}」${mentionCount}人提及，开始 embedding`, { sessionId });

      const embeddings = await embed(texts);
      const embeddingByUser: Record<string, number[]> = {};
      mentioners.forEach((uid, i) => { embeddingByUser[uid] = embeddings[i]; });

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
        const peerScores = Object.values(simMap[uid] ?? {});
        skwScoreByWordUser[word][uid] = peerScores.length > 0
          ? peerScores.reduce((a, b) => a + b, 0) / peerScores.length
          : 0.1;
      }
    }

    await updateKeywordSkwBatch(updateRows);
  }

  for (const item of candidates) {
    if (!item.needs_prompt || !item.target_user_id) continue;

    const alreadyPending = await hasPendingInfoGapKeyword(sessionId, item.target_user_id, item.word);
    if (alreadyPending) {
      logger.info(`[SKW] 「${item.word}」用户 ${item.target_user_id} 已有 pending 按钮，跳过`, { sessionId });
      continue;
    }

    const recentlyClicked = await hasClickedInfoGapKeywordInRecentWindows(
      sessionId,
      item.target_user_id,
      item.word,
      windowStart,
      RECENT_WINDOW_COUNT,
      WINDOW_MS,
    );
    if (recentlyClicked) {
      logger.info(`[SKW] 「${item.word}」用户 ${item.target_user_id} 近期已点击，跳过`, { sessionId });
      continue;
    }

    const skwScore = skwScoreByWordUser[item.word]?.[item.target_user_id] ?? 0.1;
    const buttonId = await writeInfoGapButton({
      session_id: sessionId,
      user_id: item.target_user_id,
      keyword: item.word,
      skw_score: skwScore,
      window_start: windowStart,
      llm_reason: item.reason,
    });

    if (!buttonId) {
      logger.info(`[SKW] 「${item.word}」writeInfoGapButton 未插入（ON CONFLICT），跳过`, { sessionId });
      continue;
    }

    await notifyInfoGapButton({
      session_id: sessionId,
      user_id: item.target_user_id,
      button_id: buttonId,
      keyword: item.word,
      skw_score: skwScore,
      window_start: windowStart.toISOString(),
    });

    logger.info(`[SKW] 「${item.word}」按钮已推送给用户 ${item.target_user_id}`, { sessionId });
  }

  return { keywords: words, scores };
}

export async function computeSkw(
  sessionId: string,
  windowStart: Date,
  windowEnd: Date,
  memberIds: string[],
): Promise<SkwResult> {
  const recall = await recallInfoGapKeywords(sessionId, windowStart, windowEnd, memberIds);
  return decideInfoGapButtons({
    sessionId,
    windowStart,
    memberIds,
    candidates: recall.candidates,
  });
}
