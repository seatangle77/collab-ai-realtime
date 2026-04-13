export interface PushLogLike {
  id: string
  target_user_id?: string | null
  target_user_name?: string | null
  push_content?: string | null
  triggered_at?: string | null
}

export function parsePushLogTime(value: string | undefined | null): number | null {
  if (!value) return null
  const ts = new Date(value).getTime()
  return Number.isNaN(ts) ? null : ts
}

function normalizeContent(value: string | null | undefined): string {
  return (value || '').trim()
}

export function buildPushLogDedupeKey(item: PushLogLike): string | null {
  const content = normalizeContent(item.push_content)
  if (!content) return null
  const triggeredAt = parsePushLogTime(item.triggered_at)
  const timeBucket = triggeredAt == null ? 'na' : String(Math.floor(triggeredAt / 1000))
  return [
    item.target_user_id || '',
    item.target_user_name || '',
    content,
    timeBucket,
  ].join('::')
}

export function sortPushLogsByTriggeredAtDesc<T extends PushLogLike>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const timeDiff = (parsePushLogTime(b.triggered_at) ?? 0) - (parsePushLogTime(a.triggered_at) ?? 0)
    if (timeDiff !== 0) return timeDiff
    const keyA = buildPushLogDedupeKey(a) ?? a.id
    const keyB = buildPushLogDedupeKey(b) ?? b.id
    return keyA.localeCompare(keyB)
  })
}

export function dedupePushLogs<T extends PushLogLike>(items: T[]): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = buildPushLogDedupeKey(item)
    if (!key) return false
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}
