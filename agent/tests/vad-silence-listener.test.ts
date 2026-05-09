const subscribeMock = jest.fn();
const unsubscribeMock = jest.fn();

jest.mock('../src/cache/redis-client', () => ({
  getRedisSubscriber: jest.fn(),
}));

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

import { getRedisSubscriber } from '../src/cache/redis-client';
import { VAD_SILENCE_CHANNEL, VadSilenceListener } from '../src/vad-silence-listener';

const mockGetRedisSubscriber = getRedisSubscriber as jest.MockedFunction<typeof getRedisSubscriber>;

describe('VadSilenceListener', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    subscribeMock.mockResolvedValue(undefined);
    unsubscribeMock.mockResolvedValue(undefined);
    mockGetRedisSubscriber.mockResolvedValue({
      subscribe: subscribeMock,
      unsubscribe: unsubscribeMock,
    } as never);
  });

  it('订阅 Redis 静默事件并把有效 payload 转交 handler', async () => {
    const handler = jest.fn();
    const listener = new VadSilenceListener(handler);

    await listener.start();

    expect(subscribeMock).toHaveBeenCalledWith(VAD_SILENCE_CHANNEL, expect.any(Function));

    const onMessage = subscribeMock.mock.calls[0][1];
    onMessage(JSON.stringify({
      session_id: 's1',
      silence_ms: 720,
      last_voice_at_ms: 1710000000000,
    }));
    await Promise.resolve();

    expect(handler).toHaveBeenCalledWith({
      session_id: 's1',
      silence_ms: 720,
      last_voice_at_ms: 1710000000000,
    });
  });

  it('stop 时取消订阅静默事件 channel', async () => {
    const listener = new VadSilenceListener(jest.fn());

    await listener.start();
    await listener.stop();

    expect(unsubscribeMock).toHaveBeenCalledWith(VAD_SILENCE_CHANNEL);
  });
});
