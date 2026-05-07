import { formatLogTimestamp } from '../src/logger';

describe('logger timestamp', () => {
  it('formats log timestamps in Asia/Shanghai', () => {
    expect(formatLogTimestamp(new Date('2026-05-07T07:20:00Z'))).toBe('2026-05-07 15:20:00 +08');
  });
});
