import { test, expect, type Page } from '@playwright/test'

interface MockUser {
  id: string
  name: string
  email: string
}

interface SessionRecord {
  id: string
  group_id: string
  created_at: string
  last_updated: string
  session_title: string
  status: 'not_started' | 'ongoing' | 'ended'
  created_by: string
}

const currentUser: MockUser = {
  id: 'detail-user-a',
  name: '讨论者A',
  email: 'detail-a@example.com',
}

const currentGroup = {
  id: 'detail-group',
  name: '详情群组',
}

function buildSession(status: SessionRecord['status']): SessionRecord {
  return {
    id: `session-${status}`,
    group_id: currentGroup.id,
    created_at: '2026-02-01T08:00:00.000Z',
    last_updated: '2026-02-01T08:30:00.000Z',
    session_title: `详情页-${status}`,
    status,
    created_by: currentUser.id,
  }
}

function transcript(id: string, text: string, createdAt: string) {
  return {
    transcript_id: id,
    group_id: currentGroup.id,
    session_id: id.includes('ended') ? 'session-ended' : 'session-ongoing',
    speaker: currentUser.id,
    speaker_name: currentUser.name,
    text,
    start: createdAt,
    end: createdAt,
    created_at: createdAt,
  }
}

async function seedAuth(page: Page) {
  await page.addInitScript(
    ({ user, group }) => {
      localStorage.setItem('app_access_token', 'mock-token')
      localStorage.setItem('app_user', JSON.stringify(user))
      localStorage.setItem('app_current_group', JSON.stringify(group))
    },
    { user: currentUser, group: currentGroup },
  )
}

async function installMockWs(page: Page) {
  await page.addInitScript(() => {
    const nativeSetTimeout = window.setTimeout.bind(window)
    ;(window as any).__wsAutoOpen = true
    window.setTimeout = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
      const capped = typeof timeout === 'number' ? Math.min(timeout, 100) : timeout
      return nativeSetTimeout(handler, capped, ...args)
    }) as typeof window.setTimeout

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        ;(window as any).__lastWs = this
        nativeSetTimeout(() => {
          if (!(window as any).__wsAutoOpen) {
            this.readyState = MockWebSocket.CLOSED
            this.onclose?.(new CloseEvent('close'))
            return
          }
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
          this.onmessage?.(
            new MessageEvent('message', { data: JSON.stringify({ type: 'connected', data: {} }) }),
          )
        }, 0)
      }

      send() {}

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }

      addEventListener() {}

      removeEventListener() {}

      dispatchEvent() {
        return true
      }
    }

    ;(window as any).WebSocket = MockWebSocket
    ;(window as any).__emitWsMessage = (payload: unknown) => {
      const ws = (window as any).__lastWs
      if (!ws || typeof ws.onmessage !== 'function') return
      ws.onmessage(new MessageEvent('message', { data: JSON.stringify(payload) }))
    }
    ;(window as any).__closeWs = () => {
      const ws = (window as any).__lastWs
      ws?.close()
    }
    ;(window as any).__setWsAutoOpen = (value: boolean) => {
      ;(window as any).__wsAutoOpen = value
    }
  })
}

async function mockSessionDetailApis(
  page: Page,
  session: SessionRecord,
  options: {
    transcripts?: unknown[]
    summary?: { content: string; version: number } | null
    summaries?: unknown[]
    pushLogs?: unknown[]
    infoGapButtons?: unknown[]
  } = {},
) {
  const transcripts = options.transcripts ?? [
    transcript(`${session.status}-tx-1`, '第一句转录', '2026-02-01T08:00:01.000Z'),
  ]

  const summary = options.summary ?? { content: '这是用于详情页验收的摘要。', version: 3 }
  const summaries = options.summaries ?? (
    summary
      ? [
          {
            id: `summary-v${summary.version}`,
            session_id: session.id,
            version: summary.version,
            content: summary.content,
            analysis_run_id: `summary:${session.id}:v${summary.version}`,
            window_start: '2026-02-01T08:00:00.000Z',
            window_end: '2026-02-01T08:05:00.000Z',
            created_at: '2026-02-01T08:05:00.000Z',
          },
        ]
      : []
  )
  const pushLogs = options.pushLogs ?? []
  const infoGapButtons = options.infoGapButtons ?? [{ id: 'ig-1', keyword: '风险', skw_score: 0.2 }]

  await page.route('**/api/groups/my', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: currentGroup.id,
          name: currentGroup.name,
          created_at: '2026-02-01T08:00:00.000Z',
          is_active: true,
          member_count: 3,
          my_role: 'leader',
        },
      ]),
    })
  })

  await page.route(`**/api/groups/${currentGroup.id}/sessions**`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) })
  })

  await page.route(`**/api/sessions/${session.id}/transcripts`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(transcripts) })
  })

  await page.route(`**/api/sessions/${session.id}/summary`, async (route) => {
    if (!summary) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not found' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(summary) })
  })

  await page.route(`**/api/sessions/${session.id}/summaries`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(summaries) })
  })

  await page.route(`**/api/sessions/${session.id}/push-logs`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pushLogs) })
  })

  await page.route(`**/api/sessions/${session.id}/info-gap/buttons**`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(infoGapButtons) })
  })
}

async function emitWs(page: Page, payload: object) {
  await page.evaluate((message) => {
    ;(window as any).__emitWsMessage?.(message)
  }, payload)
}

test.describe('Step 6 - AppSessionDetail UI', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page)
    await installMockWs(page)
  })

  test('ongoing session opens with transcripts in the primary viewport and collapsed summary', async ({ page }) => {
    const session = buildSession('ongoing')
    await mockSessionDetailApis(page, session, {
      infoGapButtons: [{ id: 'ig-risk', keyword: '风险', skw_score: 0.2 }],
    })

    await page.goto(`/app/sessions/${session.id}`)
    await expect(page.locator('.app-session-detail-transcripts-title')).toBeVisible()
    await expect(page.locator('.ai-sheet')).toBeVisible()
    await expect(page.locator('.ai-sheet__body')).toHaveCount(0)
    await expect(page.locator('.ai-sheet__preview-title')).toContainText('摘要')
    await expect(page.locator('.ai-sheet__preview')).toContainText('风险')

    const transcriptHeaderBox = await page.locator('.app-session-detail-transcripts').boundingBox()
    expect(transcriptHeaderBox).not.toBeNull()
    expect(transcriptHeaderBox!.y).toBeLessThan(450)
  })

  test('ended session opens with expanded summary and no sticky info-gap bar', async ({ page }) => {
    const session = buildSession('ended')
    await mockSessionDetailApis(page, session, {
      transcripts: [transcript('ended-tx-1', '复盘内容', '2026-02-01T09:00:01.000Z')],
      infoGapButtons: [{ id: 'ig-ended', keyword: '不该显示', skw_score: 0.1 }],
    })

    await page.goto(`/app/sessions/${session.id}`)
    await expect(page.locator('.ai-sheet')).toBeVisible()
    await expect(page.locator('.ai-sheet__body')).toHaveCount(0)
    await expect(page.locator('.ai-sheet__preview-title')).toContainText('摘要')
    await expect(page.locator('.ai-sheet__preview')).toContainText('不该显示')
  })

  test('history push logs only render suggestions for current user or broadcast', async ({ page }) => {
    const session = buildSession('ongoing')
    await mockSessionDetailApis(page, session, {
      pushLogs: [
        {
          id: 'push-self',
          session_id: session.id,
          target_user_id: currentUser.id,
          push_content: '这条是发给当前用户的',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-02-01T08:00:10.000Z',
        },
        {
          id: 'push-other',
          session_id: session.id,
          target_user_id: 'other-user',
          push_content: '这条是发给别人的',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-02-01T08:00:11.000Z',
        },
        {
          id: 'push-broadcast',
          session_id: session.id,
          target_user_id: null,
          push_content: '这条是广播建议',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-02-01T08:00:12.000Z',
        },
      ],
    })

    await page.goto(`/app/sessions/${session.id}`)
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '这条是发给当前用户的' })).toBeVisible()
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '这条是广播建议' })).toBeVisible()
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '这条是发给别人的' })).toHaveCount(0)
  })

  test('history push logs dedupe same-second duplicate suggestions for current user', async ({ page }) => {
    const session = buildSession('ongoing')
    await mockSessionDetailApis(page, session, {
      pushLogs: [
        {
          id: 'push-dup-1',
          session_id: session.id,
          target_user_id: currentUser.id,
          push_content: '同一秒内重复的建议',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-02-01T08:00:10.123Z',
        },
        {
          id: 'push-dup-2',
          session_id: session.id,
          target_user_id: currentUser.id,
          push_content: '同一秒内重复的建议',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-02-01T08:00:10.789Z',
        },
      ],
    })

    await page.goto(`/app/sessions/${session.id}`)
    await expect(page.locator('.app-session-detail-ai-card')).toHaveCount(1)
    await expect(page.locator('.app-session-detail-ai-card')).toContainText('同一秒内重复的建议')
  })

  test('runtime push later merged with polled history still renders a single suggestion when history includes target_user_id', async ({ page }) => {
    const session = buildSession('ongoing')
    let pushLogFetchCount = 0
    await mockSessionDetailApis(page, session, { pushLogs: [] })
    await page.unroute(`**/api/sessions/${session.id}/push-logs`)
    await page.route(`**/api/sessions/${session.id}/push-logs`, async (route) => {
      pushLogFetchCount += 1
      const body = pushLogFetchCount >= 2
        ? [
            {
              id: 'push-persisted-1',
              session_id: session.id,
              // Regression guard: history payload must keep target_user_id,
              // otherwise the UI cannot merge it with the live WS suggestion.
              target_user_id: currentUser.id,
              push_content: '实时与历史合并的建议',
              push_channel: 'web',
              delivery_status: 'delivered',
              triggered_at: '2026-02-01T08:00:15.000Z',
            },
          ]
        : []
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    })

    await page.goto(`/app/sessions/${session.id}`)
    await emitWs(page, {
      type: 'push_notification',
      data: {
        content: '实时与历史合并的建议',
        target_user_id: currentUser.id,
        triggered_at: '2026-02-01T08:00:15.000Z',
      },
    })

    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '实时与历史合并的建议' })).toHaveCount(1)
  })

  test('WS reconnect and disconnect copy stays human-readable without technical jargon', async ({ page }) => {
    const session = buildSession('ongoing')
    await mockSessionDetailApis(page, session)

    await page.goto(`/app/sessions/${session.id}`)
    await page.evaluate(() => {
      ;(window as any).__setWsAutoOpen(false)
      ;(window as any).__closeWs()
    })

    await expect(page.locator('.app-session-detail-ws-banner')).toContainText('网络不稳定，正在恢复...')
    await expect(page.locator('.app-session-detail-ws-banner')).not.toContainText('第 2 次')
    await expect(page.locator('.app-session-detail-ws-banner')).not.toContainText('WebSocket')
    await expect(page.locator('.app-session-detail-ws-banner')).not.toContainText('reconnect')

    await expect(page.locator('.app-session-detail-ws-banner')).toContainText('连接已断开', {
      timeout: 5000,
    })
    await expect(page.getByRole('button', { name: '重新连接' })).toBeVisible()
  })

  test('summary 404 and empty transcript edge case still renders the empty state safely', async ({ page }) => {
    const session = buildSession('ended')
    await mockSessionDetailApis(page, session, {
      transcripts: [],
      summary: null,
      pushLogs: [],
      infoGapButtons: [],
    })

    await page.goto(`/app/sessions/${session.id}`)
    await expect(page.locator('.ai-sheet')).toHaveCount(0)
    await expect(page.locator('.app-empty-state-title').filter({ hasText: '暂无讨论实录' })).toBeVisible()
  })
})
