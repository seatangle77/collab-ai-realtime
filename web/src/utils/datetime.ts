const TIMEZONE_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i
type DateTimeValue = string | Date | null | undefined

export function parseUtcApiDate(value: DateTimeValue): Date | null {
  if (!value) return null
  if (value instanceof Date) return value

  const normalized = value.trim().replace(' ', 'T')
  if (!normalized) return null

  const withTimezone = TIMEZONE_SUFFIX_RE.test(normalized) ? normalized : `${normalized}Z`
  const date = new Date(withTimezone)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTimeToCST(value: DateTimeValue): string {
  if (!value) return '-'
  const d = parseUtcApiDate(value)
  if (!d) {
    return typeof value === 'string' ? value : '-'
  }
  return d
    .toLocaleString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
    .replace(/\//g, '-')
}

export function formatTimeToCST(
  value: DateTimeValue,
  options: { seconds?: boolean; fallback?: string } = {},
): string {
  const fallback = options.fallback ?? '--:--'
  const d = parseUtcApiDate(value)
  if (!d) return fallback
  return d.toLocaleTimeString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    ...(options.seconds === false ? {} : { second: '2-digit' as const }),
    hour12: false,
  })
}

export function formatMonthDayTimeToCST(value: DateTimeValue, fallback = ''): string {
  const d = parseUtcApiDate(value)
  if (!d) return fallback
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
