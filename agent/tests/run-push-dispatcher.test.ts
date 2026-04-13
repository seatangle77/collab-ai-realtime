import * as queries from '../src/db/queries';
import * as nlpClient from '../src/http/nlp-client';
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
const mockHasRecentDeliveredPushWithExactContent =
  queries.hasRecentDeliveredPushWithExactContent as jest.MockedFunction<typeof queries.hasRecentDeliveredPushWithExactContent>;
const mockGetRecentDeliveredEmbeddings =
  queries.getRecentDeliveredEmbeddings as jest.MockedFunction<typeof queries.getRecentDeliveredEmbeddings>;
const mockUpdatePushQueueStatus = queries.updatePushQueueStatus as jest.MockedFunction<typeof queries.updatePushQueueStatus>;
const mockWriteDiscussionState = queries.writeDiscussionState as jest.MockedFunction<typeof queries.writeDiscussionState>;
const mockNotifyPush = nlpClient.notifyPush as jest.MockedFunction<typeof nlpClient.notifyPush>;

const SESSION = 's_test';
const QUEUE_ITEM = {
  id: 'pq_1',
  session_id: SESSION,
  target_user_id: 'uA',
  state_type: 'low_participation',
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
    mockHasRecentDeliveredPushWithExactContent.mockResolvedValue(false);
    mockGetRecentDeliveredEmbeddings.mockResolvedValue([]);
    mockWriteDiscussionState.mockResolvedValue('ds_1');
    mockNotifyPush.mockResolvedValue(undefined);
    mockUpdatePushQueueStatus.mockResolvedValue(undefined);
  });

  it('成功执行时写状态、通知并更新为 delivered', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockClaimPendingPushQueue).toHaveBeenCalledWith(SESSION, 20);
    expect(mockWriteDiscussionState).toHaveBeenCalledTimes(1);
    expect(mockNotifyPush).toHaveBeenCalledTimes(1);
    expect(mockNotifyPush).toHaveBeenCalledWith(
      SESSION,
      'uA',
      '请试着补充一个新的观点',
      'ds_1',
      'low_participation',
      'pq_1',
    );
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'delivered', expect.any(Date));
  });

  it('规则命中时更新为 skipped 且不执行推送', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(true);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped');
  });

  it('执行异常时更新为 failed', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockWriteDiscussionState.mockRejectedValue(new Error('db down'));

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'failed');
  });

  it('最近短时间已发送相同文案时跳过', async () => {
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
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped');
  });

  it('与最近同类已推内容相似度达到阈值时跳过', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockGetRecentDeliveredEmbeddings.mockResolvedValue([
      { content_embedding: [1, 0, 0] },
      { content_embedding: [0, 1, 0] },
    ]);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockGetRecentDeliveredEmbeddings).toHaveBeenCalledWith(
      SESSION,
      'uA',
      'low_participation',
      2,
    );
    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped');
  });

  it('同一轮同用户第二条待推送直接跳过', async () => {
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
    expect(mockUpdatePushQueueStatus).toHaveBeenNthCalledWith(2, 'pq_2', 'skipped');
  });
});
