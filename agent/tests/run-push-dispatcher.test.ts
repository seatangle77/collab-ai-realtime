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

const mockGetPendingPushQueue = queries.getPendingPushQueue as jest.MockedFunction<typeof queries.getPendingPushQueue>;
const mockGetRecentDeliveredEmbeddings = queries.getRecentDeliveredEmbeddings as jest.MockedFunction<typeof queries.getRecentDeliveredEmbeddings>;
const mockGetStateTypeCountInWindow = queries.getStateTypeCountInWindow as jest.MockedFunction<typeof queries.getStateTypeCountInWindow>;
const mockUpdatePushQueueStatus = queries.updatePushQueueStatus as jest.MockedFunction<typeof queries.updatePushQueueStatus>;
const mockWriteDiscussionState = queries.writeDiscussionState as jest.MockedFunction<typeof queries.writeDiscussionState>;
const mockWritePushLog = queries.writePushLog as jest.MockedFunction<typeof queries.writePushLog>;
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
    mockGetPendingPushQueue.mockResolvedValue([QUEUE_ITEM]);
    mockGetRecentDeliveredEmbeddings.mockResolvedValue([]);
    mockGetStateTypeCountInWindow.mockResolvedValue(0);
    mockWriteDiscussionState.mockResolvedValue('ds_1');
    mockWritePushLog.mockResolvedValue(undefined);
    mockNotifyPush.mockResolvedValue(undefined);
    mockUpdatePushQueueStatus.mockResolvedValue(undefined);
  });

  it('成功执行时写状态、写日志、通知并更新为 delivered', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockWriteDiscussionState).toHaveBeenCalledTimes(1);
    expect(mockWritePushLog).toHaveBeenCalledTimes(1);
    expect(mockNotifyPush).toHaveBeenCalledTimes(1);
    expect(mockWritePushLog).toHaveBeenCalledWith(expect.objectContaining({
      content_embedding: [1, 0, 0],
      delivery_status: 'delivered',
    }));
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'delivered', expect.any(Date));
  });

  it('规则命中时更新为 skipped 且不执行推送', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(true);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockWritePushLog).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped');
  });

  it('执行异常时更新为 failed', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockWriteDiscussionState.mockRejectedValue(new Error('db down'));

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'failed');
  });

  it('10 分钟内同类型已 delivered 2 次时跳过', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockGetStateTypeCountInWindow.mockResolvedValue(2);

    await dispatcher.runPushDispatcher(SESSION);

    expect(mockGetRecentDeliveredEmbeddings).not.toHaveBeenCalled();
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

    expect(mockWriteDiscussionState).not.toHaveBeenCalled();
    expect(mockNotifyPush).not.toHaveBeenCalled();
    expect(mockUpdatePushQueueStatus).toHaveBeenCalledWith('pq_1', 'skipped');
  });

  it('同一轮同用户第二条待推送直接跳过', async () => {
    jest.spyOn(dispatcher.pushDispatcherHooks, 'shouldSkipPushQueueItem').mockResolvedValue(false);
    mockGetPendingPushQueue.mockResolvedValue([
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
