import { expect, test } from '@playwright/test'
import {
  formatDateTimeToCST,
  formatMonthDayTimeToCST,
  formatTimeToCST,
  parseUtcApiDate,
} from '../../src/utils/datetime'
import { parsePushLogTime } from '../../src/utils/pushLogs'

test.describe('timezone utilities', () => {
  test('parses UTC API strings with or without timezone suffix as the same instant', () => {
    const withZ = parseUtcApiDate('2026-04-14T10:00:12Z')
    const withoutZ = parseUtcApiDate('2026-04-14T10:00:12')
    const withOffset = parseUtcApiDate('2026-04-14T18:00:12+08:00')

    expect(withZ?.toISOString()).toBe('2026-04-14T10:00:12.000Z')
    expect(withoutZ?.toISOString()).toBe('2026-04-14T10:00:12.000Z')
    expect(withOffset?.toISOString()).toBe('2026-04-14T10:00:12.000Z')
  })

  test('formats API timestamps in Asia/Shanghai', () => {
    expect(formatDateTimeToCST('2026-04-14T10:00:12Z')).toBe('2026-04-14 18:00:12')
    expect(formatDateTimeToCST('2026-04-14T10:00:12')).toBe('2026-04-14 18:00:12')
    expect(formatDateTimeToCST('2026-04-14T18:00:12+08:00')).toBe('2026-04-14 18:00:12')
    expect(formatTimeToCST('2026-04-14T10:00:12')).toBe('18:00:12')
    expect(formatTimeToCST('2026-04-14T10:00:12', { seconds: false })).toBe('18:00')
    expect(formatMonthDayTimeToCST('2026-04-14T10:00:12')).toBe('04/14 18:00')
  })

  test('uses UTC parsing for push log sorting timestamps', () => {
    const expected = Date.parse('2026-04-14T10:00:12Z')

    expect(parsePushLogTime('2026-04-14T10:00:12')).toBe(expected)
    expect(parsePushLogTime('2026-04-14T10:00:12Z')).toBe(expected)
    expect(parsePushLogTime('2026-04-14T18:00:12+08:00')).toBe(expected)
  })
})
