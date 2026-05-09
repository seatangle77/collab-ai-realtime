import { computeSkw } from '../src/skills/info-gap';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetTranscripts = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;
const mockWriteKeywordSkw = queries.writeKeywordSkw as jest.MockedFunction<
  typeof queries.writeKeywordSkw
>;
const mockUpdateKeywordSkwBatch = queries.updateKeywordSkwBatch as jest.MockedFunction<
  typeof queries.updateKeywordSkwBatch
>;
const mockDeleteKeywordSkwByKeyword = queries.deleteKeywordSkwByKeyword as jest.MockedFunction<
  typeof queries.deleteKeywordSkwByKeyword
>;
const mockWriteKeywordRecallAnalysis = queries.writeKeywordRecallAnalysis as jest.MockedFunction<
  typeof queries.writeKeywordRecallAnalysis
>;
const mockWriteInfoGapButton = queries.writeInfoGapButton as jest.MockedFunction<
  typeof queries.writeInfoGapButton
>;
const mockHasPendingInfoGapKeyword = queries.hasPendingInfoGapKeyword as jest.MockedFunction<
  typeof queries.hasPendingInfoGapKeyword
>;
const mockHasEverPushedInfoGapKeyword =
  queries.hasEverPushedInfoGapKeyword as jest.MockedFunction<
    typeof queries.hasEverPushedInfoGapKeyword
  >;
const mockGetRecentInfoGapKeywordsForUser =
  queries.getRecentInfoGapKeywordsForUser as jest.MockedFunction<
    typeof queries.getRecentInfoGapKeywordsForUser
  >;
const mockKeywordRecallWithGap = nlp.keywordRecallWithGap as jest.MockedFunction<
  typeof nlp.keywordRecallWithGap
>;
const mockEmbed = nlp.embed as jest.MockedFunction<typeof nlp.embed>;
const mockSimilarity = nlp.similarity as jest.MockedFunction<typeof nlp.similarity>;
const mockNotifyInfoGapButton = nlp.notifyInfoGapButton as jest.MockedFunction<
  typeof nlp.notifyInfoGapButton
>;

const SESSION = 's_test';
const MEMBERS = ['u1', 'u2'];
const WIN_START = new Date('2024-01-01T10:00:00Z');
const WIN_END   = new Date('2024-01-01T10:02:00Z');

function makeTranscript(userId: string, text: string) {
  return { transcript_id: 'tr_x', user_id: userId, speaker_name: null, text,
           start: WIN_START, end: WIN_END, duration: 10 };
}

function makeRecall(
  words: Array<{
    word: string;
    needs_prompt?: boolean;
    target_user_id?: string;
    reason?: string;
  }>,
) {
  return {
    keywords: words.map(({ word, needs_prompt = false, target_user_id = '', reason = '' }) => ({
      word,
      needs_prompt,
      target_user_id,
      reason,
    })),
  };
}

function getAllUpdatedRows() {
  return mockUpdateKeywordSkwBatch.mock.calls.flatMap((call) => call[0]);
}

describe('info-gap / computeSkw', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockKeywordRecallWithGap.mockResolvedValue({ keywords: [] });
    mockWriteKeywordSkw.mockResolvedValue(undefined);
    mockUpdateKeywordSkwBatch.mockResolvedValue(undefined);
    mockDeleteKeywordSkwByKeyword.mockResolvedValue(undefined);
    mockWriteKeywordRecallAnalysis.mockResolvedValue(undefined);
    mockWriteInfoGapButton.mockResolvedValue('igb_mock');
    mockHasPendingInfoGapKeyword.mockResolvedValue(false);
    mockHasEverPushedInfoGapKeyword.mockResolvedValue(false);
    mockGetRecentInfoGapKeywordsForUser.mockResolvedValue([]);
    mockNotifyInfoGapButton.mockResolvedValue(undefined);
  });

  it('成员 < 2：直接返回空结果，不调用 NLP', async () => {
    const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, ['u1']);
    expect(keywords).toEqual([]);
    expect(scores).toEqual({});
    expect(mockKeywordRecallWithGap).not.toHaveBeenCalled();
    expect(mockWriteKeywordSkw).not.toHaveBeenCalled();
    expect(mockUpdateKeywordSkwBatch).not.toHaveBeenCalled();
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
  });

  it('无人发言：返回空结果', async () => {
    mockGetTranscripts.mockResolvedValue([]);
    const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);
    expect(keywords).toEqual([]);
    expect(scores).toEqual({});
    expect(mockKeywordRecallWithGap).not.toHaveBeenCalled();
    expect(mockWriteKeywordSkw).not.toHaveBeenCalled();
    expect(mockUpdateKeywordSkwBatch).not.toHaveBeenCalled();
    expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
  });

  it('历史 pending 按钮不会被自动过期：新窗口仍正常写入并推送按钮', async () => {
    mockGetTranscripts.mockResolvedValue([
      makeTranscript('u1', '我们聊 AI'),
      makeTranscript('u2', '我也聊 AI'),
    ]);
    mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
      { word: 'AI', needs_prompt: true, target_user_id: 'u1', reason: '需要追问' },
    ]));
    mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
    mockSimilarity.mockResolvedValue([0.75]);

    await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

    expect(mockWriteInfoGapButton).toHaveBeenCalledTimes(1);
    expect(mockNotifyInfoGapButton).toHaveBeenCalledTimes(1);
  });

  describe('阶段一：关键词召回', () => {
    it('大模型返回空关键词：终止，不写任何 DB', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '人工智能技术很重要'),
        makeTranscript('u2', '机器学习是核心'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue({ keywords: [] });

      const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(keywords).toEqual([]);
      expect(scores).toEqual({});
      expect(mockKeywordRecallWithGap).toHaveBeenCalledWith({
        u1: '人工智能技术很重要',
        u2: '机器学习是核心',
      });
      expect(mockWriteKeywordSkw).not.toHaveBeenCalled();
      expect(mockUpdateKeywordSkwBatch).not.toHaveBeenCalled();
      expect(mockDeleteKeywordSkwByKeyword).not.toHaveBeenCalled();
      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('大模型调用失败时：按当前实现视为返回空关键词，整体结束', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我提到了 AI'),
        makeTranscript('u2', '我提到了 Agent'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue({ keywords: [] });

      const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(keywords).toEqual([]);
      expect(scores).toEqual({});
      expect(mockKeywordRecallWithGap).toHaveBeenCalledWith({
        u1: '我提到了 AI',
        u2: '我提到了 Agent',
      });
      expect(mockWriteKeywordSkw).not.toHaveBeenCalled();
      expect(mockUpdateKeywordSkwBatch).not.toHaveBeenCalled();
      expect(mockDeleteKeywordSkwByKeyword).not.toHaveBeenCalled();
      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });
  });

  describe('阶段二：pending 初始写入', () => {
    it('2人1词：writeKeywordSkw 写入 1 条 pending 记录', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteKeywordSkw).toHaveBeenCalledTimes(1);
      const rows = mockWriteKeywordSkw.mock.calls[0][0];
      expect(rows).toHaveLength(1);
      expect(rows[0]).toEqual(expect.objectContaining({
        session_id: SESSION,
        keyword: 'AI',
        user_a_id: 'u1',
        user_b_id: 'u2',
        skw_status: 'pending',
        skw_score: undefined,
        mention_count: undefined,
      }));
    });

    it('3人1词：writeKeywordSkw 写入 3 条 pending 记录', async () => {
      const members3 = ['u1', 'u2', 'u3'];
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '大家都在聊 AI'),
        makeTranscript('u2', 'AI 确实重要'),
        makeTranscript('u3', '我也提到 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2], [0.6, 0.4]]);
      mockSimilarity.mockResolvedValue([0.9, 0.8, 0.7]);

      await computeSkw(SESSION, WIN_START, WIN_END, members3);

      const rows = mockWriteKeywordSkw.mock.calls[0][0];
      expect(rows).toHaveLength(3);
      expect(rows.map((row) => `${row.user_a_id}-${row.user_b_id}`)).toEqual([
        'u1-u2',
        'u1-u3',
        'u2-u3',
      ]);
      expect(rows.every((row) => row.keyword === 'AI')).toBe(true);
      expect(rows.every((row) => row.skw_status === 'pending')).toBe(true);
    });

    it('3人3词：writeKeywordSkw 写入 9 条 pending 记录', async () => {
      const members3 = ['u1', 'u2', 'u3'];
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', 'AI Agent MVP'),
        makeTranscript('u2', 'AI Agent MVP'),
        makeTranscript('u3', 'AI Agent MVP'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI' },
        { word: 'Agent' },
        { word: 'MVP' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2], [0.6, 0.4]]);
      mockSimilarity.mockResolvedValue([0.9, 0.8, 0.7]);

      await computeSkw(SESSION, WIN_START, WIN_END, members3);

      const rows = mockWriteKeywordSkw.mock.calls[0][0];
      expect(rows).toHaveLength(9);
      expect(rows.every((row) => row.skw_status === 'pending')).toBe(true);
      expect(new Set(rows.map((row) => row.keyword))).toEqual(new Set(['AI', 'Agent', 'MVP']));
    });
  });

  describe('阶段三：SKW 分数计算与更新', () => {
    it('2人都提及同一词：updateKeywordSkwBatch 写入 computed', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我理解 AI 是效率工具'),
        makeTranscript('u2', '我也觉得 AI 能提升效率'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);

      const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockUpdateKeywordSkwBatch).toHaveBeenCalledTimes(1);
      expect(getAllUpdatedRows()).toEqual([
        expect.objectContaining({
          skw_score: 0.75,
          mention_count: 2,
          skw_status: 'computed',
        }),
      ]);
      expect(scores.AI.u1.u2).toBeCloseTo(0.75);
      expect(scores.AI.u2.u1).toBeCloseTo(0.75);
    });

    it('只有1人提及：不调 embed/similarity，updateKeywordSkwBatch 写入 3 条 single_mention', async () => {
      const members3 = ['u1', 'u2', 'u3'];
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我只提到搭子'),
        makeTranscript('u2', '我没提那个词，但我有发言'),
        makeTranscript('u3', '我也没提那个词，但我也有发言'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: '搭子' }]));

      const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, members3);

      expect(mockEmbed).not.toHaveBeenCalled();
      expect(mockSimilarity).not.toHaveBeenCalled();
      const rows = getAllUpdatedRows();
      expect(rows).toHaveLength(3);
      expect(rows.every((row) => row.skw_status === 'single_mention')).toBe(true);
      expect(rows.every((row) => row.skw_score === 0.1)).toBe(true);
      expect(rows.every((row) => row.mention_count === 1)).toBe(true);
      expect(scores['搭子'].u1.u2).toBeCloseTo(0.1);
      expect(scores['搭子'].u2.u1).toBeCloseTo(0.1);
      expect(scores['搭子'].u1.u3).toBeCloseTo(0.1);
      expect(scores['搭子'].u3.u1).toBeCloseTo(0.1);
    });

    it('2人提及、1人未提及（三人场景）：1 条 computed + 2 条 single_mention', async () => {
      const members3 = ['u1', 'u2', 'u3'];
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我提到话题'),
        makeTranscript('u2', '我也提到话题'),
        makeTranscript('u3', '我在说别的内容'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: '话题' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.6, 0.4]]);
      mockSimilarity.mockResolvedValue([0.65]);

      const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, members3);

      const rows = getAllUpdatedRows();
      expect(rows).toHaveLength(3);
      expect(rows.filter((row) => row.skw_status === 'computed')).toHaveLength(1);
      expect(rows.filter((row) => row.skw_status === 'single_mention')).toHaveLength(2);
      expect(scores['话题'].u1.u2).toBeCloseTo(0.65);
      expect(scores['话题'].u1.u3).toBeCloseTo(0.1);
      expect(scores['话题'].u2.u3).toBeCloseTo(0.1);
    });

    it('3人都提及：updateKeywordSkwBatch 写入 3 条 computed，embed/similarity 各调 1 次', async () => {
      const members3 = ['u1', 'u2', 'u3'];
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', 'AI 在这里'),
        makeTranscript('u2', 'AI 在那里'),
        makeTranscript('u3', 'AI 在别处'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2], [0.6, 0.4]]);
      mockSimilarity.mockResolvedValue([0.9, 0.8, 0.7]);

      await computeSkw(SESSION, WIN_START, WIN_END, members3);

      expect(mockEmbed).toHaveBeenCalledTimes(1);
      expect(mockSimilarity).toHaveBeenCalledTimes(1);
      const rows = getAllUpdatedRows();
      expect(rows).toHaveLength(3);
      expect(rows.every((row) => row.skw_status === 'computed')).toBe(true);
      expect(rows.every((row) => row.mention_count === 3)).toBe(true);
    });

    it('大模型幻觉词（0人实际提及）：deleteKeywordSkwByKeyword 被调用，且返回 keywords 保留原召回词', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '这里没有相关内容'),
        makeTranscript('u2', '这里也没有相关内容'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI' }]));

      const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(keywords).toEqual(['AI']);
      expect(scores).toEqual({ AI: {} });
      expect(mockDeleteKeywordSkwByKeyword).toHaveBeenCalledWith(SESSION, WIN_START, 'AI');
      expect(mockUpdateKeywordSkwBatch).not.toHaveBeenCalled();
    });

    it('scores 对称性：scores[kw][a][b] === scores[kw][b][a]', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我理解话题A中的话题'),
        makeTranscript('u2', '我理解话题B中的话题'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: '话题' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.5, 0.5]]);
      mockSimilarity.mockResolvedValue([0.65]);

      const { scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(scores['话题'].u1.u2).toBeCloseTo(0.65);
      expect(scores['话题'].u2.u1).toBeCloseTo(0.65);
    });

    it('混合词（1个幻觉词 + 1个正常词）：幻觉词删除，正常词更新', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI' }, { word: '幻觉词' }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.72]);

      const { keywords, scores } = await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(keywords).toEqual(['AI', '幻觉词']);
      expect(mockDeleteKeywordSkwByKeyword).toHaveBeenCalledWith(SESSION, WIN_START, '幻觉词');
      expect(getAllUpdatedRows()).toEqual([
        expect.objectContaining({
          skw_score: 0.72,
          mention_count: 2,
          skw_status: 'computed',
        }),
      ]);
      expect(scores.AI.u1.u2).toBeCloseTo(0.72);
      expect(scores['幻觉词']).toEqual({});
    });
  });

  describe('阶段四：info_gap_buttons 写入与推送', () => {
    it('needs_prompt=false：不写 info_gap_buttons，不推送', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([{ word: 'AI', needs_prompt: false }]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('needs_prompt=true：writeInfoGapButton 和 notifyInfoGapButton 各调 1 次，数据完整且 skw_score 为真实值', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我理解 AI 是效率工具'),
        makeTranscript('u2', '我也觉得 AI 能提升效率'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI', needs_prompt: true, target_user_id: 'u1', reason: 'u1 可以进一步展开 AI 视角' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);
      mockWriteInfoGapButton.mockResolvedValue('igb_123');

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteInfoGapButton).toHaveBeenCalledWith({
        session_id: SESSION,
        user_id: 'u1',
        keyword: 'AI',
        skw_score: 0.75,
        window_start: WIN_START,
        llm_reason: 'u1 可以进一步展开 AI 视角',
      });
      expect(mockNotifyInfoGapButton).toHaveBeenCalledWith({
        session_id: SESSION,
        user_id: 'u1',
        button_id: 'igb_123',
        keyword: 'AI',
        skw_score: 0.75,
        window_start: WIN_START.toISOString(),
      });
    });

    it('target_user_id 已有 pending 按钮：跳过，不写不推', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI', needs_prompt: true, target_user_id: 'u1', reason: '需要追问' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);
      mockHasPendingInfoGapKeyword.mockResolvedValue(true);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('本会话已推送过同一关键词：跳过，不写不推', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI', needs_prompt: true, target_user_id: 'u1', reason: '需要追问' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);
      mockHasEverPushedInfoGapKeyword.mockResolvedValue(true);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockHasEverPushedInfoGapKeyword).toHaveBeenCalledWith(SESSION, 'u1', 'AI');
      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('近期已有语义相似关键词：跳过，不写不推', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊玩抽象'),
        makeTranscript('u2', '我也聊玩抽象'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: '玩抽象', needs_prompt: true, target_user_id: 'u1', reason: '需要追问' },
      ]));
      mockEmbed
        .mockResolvedValueOnce([[1, 0], [0.8, 0.2]])
        .mockResolvedValueOnce([[0.95, 0.05], [0.94, 0.06]]);
      mockSimilarity
        .mockResolvedValueOnce([0.75])
        .mockResolvedValueOnce([0.91]);
      mockGetRecentInfoGapKeywordsForUser.mockResolvedValue(['搞抽象']);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockGetRecentInfoGapKeywordsForUser).toHaveBeenCalledWith(
        SESSION,
        'u1',
      );
      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('近期相似关键词检查失败：fail open，继续写入并推送', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊玩抽象'),
        makeTranscript('u2', '我也聊玩抽象'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: '玩抽象', needs_prompt: true, target_user_id: 'u1', reason: '需要追问' },
      ]));
      mockEmbed
        .mockResolvedValueOnce([[1, 0], [0.8, 0.2]])
        .mockRejectedValueOnce(new Error('embed failed'));
      mockSimilarity.mockResolvedValueOnce([0.75]);
      mockGetRecentInfoGapKeywordsForUser.mockResolvedValue(['搞抽象']);
      mockWriteInfoGapButton.mockResolvedValue('igb_similar_fail_open');

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteInfoGapButton).toHaveBeenCalledWith(expect.objectContaining({
        session_id: SESSION,
        user_id: 'u1',
        keyword: '玩抽象',
      }));
      expect(mockNotifyInfoGapButton).toHaveBeenCalledWith(expect.objectContaining({
        session_id: SESSION,
        user_id: 'u1',
        button_id: 'igb_similar_fail_open',
        keyword: '玩抽象',
      }));
    });

    it('writeInfoGapButton 返回 null（ON CONFLICT）：不调 notifyInfoGapButton', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI', needs_prompt: true, target_user_id: 'u1', reason: '需要追问' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);
      mockWriteInfoGapButton.mockResolvedValue(null);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteInfoGapButton).toHaveBeenCalledTimes(1);
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('needs_prompt=true 但 target_user_id 为空字符串：跳过', async () => {
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', '我们聊 AI'),
        makeTranscript('u2', '我也聊 AI'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI', needs_prompt: true, target_user_id: '', reason: '缺少目标用户' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2]]);
      mockSimilarity.mockResolvedValue([0.75]);

      await computeSkw(SESSION, WIN_START, WIN_END, MEMBERS);

      expect(mockWriteInfoGapButton).not.toHaveBeenCalled();
      expect(mockNotifyInfoGapButton).not.toHaveBeenCalled();
    });

    it('3人都提及时，按钮写入的 skw_score 是 target_user_id 对其他提及者分数的平均值', async () => {
      const members3 = ['u1', 'u2', 'u3'];
      mockGetTranscripts.mockResolvedValue([
        makeTranscript('u1', 'AI 在这里'),
        makeTranscript('u2', 'AI 在那里'),
        makeTranscript('u3', 'AI 在别处'),
      ]);
      mockKeywordRecallWithGap.mockResolvedValue(makeRecall([
        { word: 'AI', needs_prompt: true, target_user_id: 'u1', reason: '让 u1 继续展开' },
      ]));
      mockEmbed.mockResolvedValue([[1, 0], [0.8, 0.2], [0.6, 0.4]]);
      mockSimilarity.mockResolvedValue([0.9, 0.8, 0.7]);

      await computeSkw(SESSION, WIN_START, WIN_END, members3);

      const writeArg = mockWriteInfoGapButton.mock.calls[0][0];
      expect(writeArg.user_id).toBe('u1');
      expect(writeArg.keyword).toBe('AI');
      expect(writeArg.skw_score).toBeCloseTo(0.85);

      const notifyArg = mockNotifyInfoGapButton.mock.calls[0][0];
      expect(notifyArg.user_id).toBe('u1');
      expect(notifyArg.keyword).toBe('AI');
      expect(notifyArg.skw_score).toBeCloseTo(0.85);
    });
  });
});
