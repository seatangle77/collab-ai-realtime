import * as queries from '../src/db/queries';
import * as nlpClient from '../src/http/nlp-client';
import * as filterModule from '../src/skills/push/run-push-filter-chain';
import * as dispatcher from '../src/skills/run-push-dispatcher';

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockClaimPendingPushQueue = queries.claimPendingPushQueue as jest.MockedFunction<typeof queries.claimPendingPushQueue>;
const mockGetPendingPushQueue = queries.getPendingPushQueue as jest.MockedFunction<typeof queries.getPendingPushQueue>;
const mockHasRecentDeliveredPushWithExactContent =
  queries.hasRecentDeliveredPushWithExactContent as jest.MockedFunction<typeof queries.hasRecentDeliveredPushWithExactContent>;
const mockGetRecentDeliveredEmbeddings =
  queries.getRecentDeliveredEmbeddings as jest.MockedFunction<typeof queries.getRecentDeliveredEmbeddings>;
const mockUpdatePushQueueStatus = queries.updatePushQueueStatus as jest.MockedFunction<typeof queries.updatePushQueueStatus>;
const mockRecoverStaleProcessingItems = queries.recoverStaleProcessingItems as jest.MockedFunction<typeof queries.recoverStaleProcessingItems>;
const mockWritePushLog = queries.writePushLog as jest.MockedFunction<typeof queries.writePushLog>;
const mockWriteDiscussionState = queries.writeDiscussionState as jest.MockedFunction<typeof queries.writeDiscussionState>;
const mockFindDiscussionStateByQueuedPushId =
  queries.findDiscussionStateByQueuedPushId as jest.MockedFunction<typeof queries.findDiscussionStateByQueuedPushId>;
const mockNotifyPush = nlpClient.notifyPush as jest.MockedFunction<typeof nlpClient.notifyPush>;
const mockCheckVadSpeaking = nlpClient.checkVadSpeaking as jest.MockedFunction<typeof nlpClient.checkVadSpeaking>;

const SESSION = 's_test';
const QUEUE_ITEM = {
  id: 'pq_1',
  session_id: SESSION,
  target_user_id: 'uA',
  state_type: 'stagnation',
  push_content: '请试着补充一个新的观点',
  content_embedding: [1, 0, 0],
  analysis_window_start: new Date('2024-01-01T10:00:00Z'),
  status: 'pending' as const,
  created_at: new Date('2024-01-01T10:01:00Z'),
  delivered_at: null,
};

describe('runPushDispatcher', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockClaimPendingPushQueue.mockResolvedValue([QUEUE_ITEM]);
    mockGetPendingPushQueue.mockResolvedValue([]);
    mockHasRecentDeliveredPushWithExactContent.mockResolvedValue(false);
    mockGetRecentDeliveredEmbeddings.mockResolvedValue([]);
    mockCheckVadSpeaking.mockResolvedValue(false);
    mockFindDiscussionStateByQueuedPushId.mockResolvedValue(null);
    mockWriteDiscussionState.mockResolvedValue('ds_1');
    mockWritePushLog.mockResolvedValue(undefined);
    mockNotifyPush.mockResolvedValue({
      id: 'pl_1',
      delivery_status: 'delivered',
      delivery_reason: 'ws_delivered',
      ws_sent: true,
    });
    mockUpdatePushQueueStatus.mockResolvedValue(undefined);
    mockRecoverStaleProcessingItems.mockResolvedValue(0);
  });

  // ─── 已有用例 ──────────────────────────────────────────────────────────────

  it('成功执行时写状态、通知并更新为 delivered', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockClaimPendingPushQueue).toHaveBeenCalledWith(SESSION, 20);
    expect(mockFindDiscussionStateByQueuedPushId).toHaveBeenCalledWith({
      sessionId: SESSION,
      queueId: 'pq_1',
    });
    expect(mockWriteDiscussionState).toHaveBeenCalledTimes(1);
    expect(mockNotifyPush).toHaveBeenCalledTimes(1);
    expect(mockNotifyPush).toHaveBeenCalledWith(
      SESSION,
      'uA',
      '请试着补充一个新的观点',
      'ds_1',
      'stagnation',
      'pq_1',
    );
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'delivered', expect.any(Date));
  });

  it('已存在 discussion_state 时复用已有 state_id', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockFindDiscussionStateByQueuedPushId.mockResolvedValue({
      id: 'ds_existing',
      session_id: SESSION,
      state_type: 'stagnation',
      target_user_id: 'uA',
      trigger_metrics: { queued_push_id: 'pq_1' },
      window_start: new Date('2024-01-01T10:00:00Z'),
    });

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).toHaveBeenCalledWith(
      SESSION,
      'uA',
      '请试着补充一个新的观点',
      'ds_existing',
      'stagnation',
      'pq_1',
    );
  });

  it('hook 规则命中时更新为 skipped + skip_reason=filter_hook 且不执行推送', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(true);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped', undefined, 'filter_hook');
  });

  it('执行异常时更新为 failed', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockWriteDiscussionState.mockRejectedValue(new Error('db down'));

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'failed', undefined, 'dispatch_exception');
  });

  it('WebSocket 未命中用户连接时回到 pending 等待下轮重试', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockNotifyPush.mockResolvedValue({
      id: 'pl_failed',
      delivery_status: 'failed',
      delivery_reason: 'ws_user_not_connected',
      ws_sent: false,
    });

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockNotifyPush).toHaveBeenCalledTimes(1);
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'pending', undefined, undefined);
  });

  it('最近短时间已发送相同文案时跳过，skip_reason=filter_exact_content', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockHasRecentDeliveredPushWithExactContent.mockResolvedValue(true);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockHasRecentDeliveredPushWithExactContent).toHaveBeenCalledWith(
      SESSION,
      'uA',
      '请试着补充一个新的观点',
      10 * 60 * 1000,
    );
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped', undefined, 'filter_exact_content');
  });

  it('与最近同类已推内容相似度达到阈值时跳过，skip_reason=filter_similar_content', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockGetRecentDeliveredEmbeddings.mockResolvedValue([
      { content_embedding: [1, 0, 0] },
      { content_embedding: [0, 1, 0] },
    ]);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockGetRecentDeliveredEmbeddings).toHaveBeenCalledWith(
      SESSION,
      'uA',
      ['stagnation', 'shallow'],
      2,
    );
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped', undefined, 'filter_similar_content');
  });

  it('同一轮同用户第二条待推送直接跳过，skip_reason=filter_same_round', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockClaimPendingPushQueue.mockResolvedValue([
      QUEUE_ITEM,
      {
        ...QUEUE_ITEM,
        id: 'pq_2',
        push_content: '请再补充一个例子',
        content_embedding: [0, 1, 0],
      },
    ]);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockWriteDiscussionState).toHaveBeenCalledTimes(1);
    expect(mockNotifyPush).toHaveBeenCalledTimes(1);
    expect(mockUpdatePushQueueStatus).toHaveBeenNthCalledWith(1, 'pq_1', 'delivered', expect.any(Date));
    expect(mockUpdatePushQueueStatus).toHaveBeenNthCalledWith(2, 'pq_2', 'skipped', undefined, 'filter_same_round');
  });

  // ─── 新增用例 ──────────────────────────────────────────────────────────────

  it('VAD 检测到有人说话时，push_queue 写 deferred + skip_reason=filter_vad_speaking', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockCheckVadSpeaking.mockResolvedValue(true);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'deferred', undefined, 'filter_vad_speaking');
  });

  it('过滤链内部抛异常时，push_queue 写 deferred + skip_reason=filter_error', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    // 让 exact content 过滤器内部抛异常，filter chain 会 catch 并返回 defer
    mockHasRecentDeliveredPushWithExactContent.mockRejectedValue(new Error('db timeout'));

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'deferred', undefined, 'filter_error');
  });

  it('过滤拦截时只更新队列状态，不写 push_logs', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockHasRecentDeliveredPushWithExactContent.mockResolvedValue(true);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped', undefined, 'filter_exact_content');
    expect(mockWritePushLog).not.toHaveBeenCalled();
  });

  it('投递返回 queue_already_final 时写 failed + skip_reason=queue_already_final', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockNotifyPush.mockResolvedValue({
      id: null,
      delivery_status: 'failed',
      delivery_reason: 'queue_already_final',
      ws_sent: false,
    });

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockNotifyPush).toHaveBeenCalledTimes(1);
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'failed', undefined, 'queue_already_final');
  });

  it('启动时调用僵尸条目恢复，超时阈值为 5 分钟', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockClaimPendingPushQueue.mockResolvedValue([]);
    mockGetPendingPushQueue.mockResolvedValue([]);
    mockRecoverStaleProcessingItems.mockResolvedValue(2);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockRecoverStaleProcessingItems).toHaveBeenCalledWith(SESSION, 5 * 60 * 1000);
  });

  it('队列为空时，不写任何状态和日志', async () => {
    mockClaimPendingPushQueue.mockResolvedValue([]);
    mockGetPendingPushQueue.mockResolvedValue([]);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockUpdatePushQueueStatus).not.toHaveBeenCalled();
    expect(mockWritePushLog).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
  });
});
