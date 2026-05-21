jest.mock('../src/config', () => ({
  config: {
    agent: {
      sessionPollMs: 15_000,
    },
  },
}));

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

jest.mock('../src/db/queries', () => ({
  getOngoingSessions: jest.fn(),
}));

jest.mock('../src/session-worker', () => ({
  SessionWorker: jest.fn().mockImplementation(() => ({
    start: jest.fn(),
    stop: jest.fn(),
    onVadSilenceAvailable: jest.fn(),
  })),
}));

import { getOngoingSessions } from '../src/db/queries';
import { SessionManager } from '../src/session-manager';
import { SessionWorker } from '../src/session-worker';

const MockSessionWorker = SessionWorker as jest.MockedClass<typeof SessionWorker>;
const mockGetOngoingSessions = getOngoingSessions as jest.MockedFunction<typeof getOngoingSessions>;

describe('SessionManager VAD silence events', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.resetAllMocks();
    mockGetOngoingSessions.mockResolvedValue([]);
    MockSessionWorker.mockImplementation(() => ({
      start: jest.fn(),
      stop: jest.fn(),
      onVadSilenceAvailable: jest.fn(),
    }) as never);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('把 VAD 静默事件转发给对应 session worker', async () => {
    mockGetOngoingSessions.mockResolvedValueOnce([
      { id: 's1', started_at: new Date('2026-04-22T10:00:00Z') },
    ] as never);

    const manager = new SessionManager();
    manager.start();
    await Promise.resolve();

    const event = { session_id: 's1', silence_ms: 600, last_voice_at_ms: 1713779970000 };
    manager.triggerVadSilence(event);

    const worker = MockSessionWorker.mock.results[0].value;
    expect(worker.onVadSilenceAvailable).toHaveBeenCalledTimes(1);
    expect(worker.onVadSilenceAvailable).toHaveBeenCalledWith(event);

    manager.stop();
  });

  it('未知 session 的 VAD 静默事件会被忽略', () => {
    const manager = new SessionManager();

    expect(() => manager.triggerVadSilence({ session_id: 'missing-session' })).not.toThrow();
  });
});
