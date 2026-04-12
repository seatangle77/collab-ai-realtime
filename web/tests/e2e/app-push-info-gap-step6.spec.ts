import { test, expect, type Page } from '@playwright/test'

const user = {
  id: 'push-step6-user',
  name: 'Push 用户',
  email: 'push-step6@example.com',
}

const group = {
  id: 'push-step6-group',
  name: 'Push Step6 群组',
}

const session = {
  id: 'push-step6-session',
  group_id: group.id,
  created_at: '2026-03-01T10:00:00.000Z',
  last_updated: '2026-03-01T10:05:00.000Z',
  session_title: 'Push + InfoGap Step6',
  status: 'ongoing',
  created_by: user.id,
}

async function seedAuth(page: Page) {
  await page.addInitScript(
    ({ seededUser, seededGroup }) => {
      localStorage.setItem('app_access_token', 'mock-token')
      localStorage.setItem('app_user', JSON.stringify(seededUser))
      localStorage.setItem('app_current_group', JSON.stringify(seededGroup))
    },
    { seededUser: user, seededGroup: group },
  )
}

async function installMockWs(page: Page) {
  await page.addInitScript(() => {
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
        setTimeout(() => {
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
  })
}

async function mockApis(
  page: Page,
  options: {
    pushLogs?: unknown[]
    infoGapButtons?: unknown[]
    transcripts?: unknown[]
    clickShouldFail?: boolean
  } = {},
) {
  const pushLogs = options.pushLogs ?? []
  const infoGapButtons = options.infoGapButtons ?? []
  const transcripts =
    options.transcripts ??
    [
      {
        transcript_id: 'tx-p1',
        group_id: group.id,
        session_id: session.id,
        speaker: user.id,
        speaker_name: user.name,
        text: '先说第一个观点。',
        start: '2026-03-01T10:00:01.000Z',
        end: '2026-03-01T10:00:03.000Z',
        created_at: '2026-03-01T10:00:03.000Z',
      },
      {
        transcript_id: 'tx-p2',
        group_id: group.id,
        session_id: session.id,
        speaker: user.id,
        speaker_name: user.name,
        text: '再说第二个观点。',
        start: '2026-03-01T10:00:05.000Z',
        end: '2026-03-01T10:00:07.000Z',
        created_at: '2026-03-01T10:00:07.000Z',
      },
    ]

  await page.route('**/api/groups/my', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: group.id,
          name: group.name,
          created_at: '2026-03-01T10:00:00.000Z',
          is_active: true,
          member_count: 2,
          my_role: 'leader',
        },
      ]),
    })
  })

  await page.route(`**/api/groups/${group.id}/sessions**`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) })
  })

  await page.route(`**/api/sessions/${session.id}/transcripts`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(transcripts) })
  })

  await page.route(`**/api/sessions/${session.id}/summary`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ content: 'Push & InfoGap 测试摘要', version: 1 }),
    })
  })

  await page.route(`**/api/sessions/${session.id}/push-logs`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pushLogs) })
  })

  await page.route(`**/api/sessions/${session.id}/info-gap/buttons`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(infoGapButtons) })
  })

  await page.route(`**/api/sessions/${session.id}/info-gap/click`, async (route) => {
    if (options.clickShouldFail) {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'mock failure' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
  })
}

async function emitWs(page: Page, payload: object) {
  await page.waitForFunction(
    () =>
      typeof (window as any).__appSessionDetailInjectWsMessage === 'function' ||
      typeof (window as any).__emitWsMessage === 'function',
    undefined,
    { timeout: 10000 },
  )
  await page.evaluate((message) => {
    const inject = (window as any).__appSessionDetailInjectWsMessage
    if (typeof inject === 'function') {
      inject(message)
      return
    }
    ;(window as any).__emitWsMessage?.(message)
  }, payload)
}

async function waitForDetailReady(page: Page) {
  await expect(page.locator('.app-session-detail-title')).toBeVisible()
  await expect(page.locator('.app-session-detail-transcripts-list')).toBeVisible()
}

test.describe('Step 6 - Push and InfoGap behaviors', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page)
    await installMockWs(page)
  })

  test('runtime push notifications only render current-user and broadcast suggestions', async ({ page }) => {
    await mockApis(page)
    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)

    await emitWs(page, {
      type: 'push_notification',
      data: { content: '发给当前用户', target_user_id: user.id, triggered_at: '2026-03-01T10:00:04.000Z' },
    })
    await emitWs(page, {
      type: 'push_notification',
      data: { content: '广播消息', target_user_id: null, triggered_at: '2026-03-01T10:00:06.000Z' },
    })
    await emitWs(page, {
      type: 'push_notification',
      data: { content: '发给别人', target_user_id: 'other-user', triggered_at: '2026-03-01T10:00:08.000Z' },
    })

    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '发给当前用户' })).toBeVisible()
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '广播消息' })).toBeVisible()
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '发给别人' })).toHaveCount(0)
  })

  test('timeline keeps transcript and AI suggestions in chronological order for extreme interleaving', async ({ page }) => {
    await mockApis(page, {
      pushLogs: [
        {
          id: 'push-mid',
          session_id: session.id,
          target_user_id: user.id,
          push_content: '中间插入的建议',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-03-01T10:00:04.000Z',
        },
      ],
    })

    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)
    await expect(page.locator('.app-session-detail-transcripts-list > li')).toHaveCount(3)

    const orderedTexts = await page.locator('.app-session-detail-transcripts-list > li').evaluateAll((items) =>
      items.map((item) => item.textContent?.replace(/\s+/g, ' ').trim() ?? ''),
    )

    expect(orderedTexts[0]).toContain('先说第一个观点')
    expect(orderedTexts[1]).toContain('中间插入的建议')
    expect(orderedTexts[2]).toContain('再说第二个观点')
  })

  test('duplicate info-gap ids are de-duplicated and toolbar hides after the last successful click', async ({ page }) => {
    await mockApis(page, {
      infoGapButtons: [{ id: 'seed-gap', keyword: '预算', skw_score: 0.1 }],
    })
    await page.goto(`/app/sessions/${session.id}`)

    await expect(page.locator('.app-session-detail-info-gap-sticky')).toBeVisible()
    await emitWs(page, {
      type: 'info_gap_button',
      data: {
        buttons: [
          { id: 'seed-gap', keyword: '预算', skw_score: 0.1 },
          { id: 'new-gap', keyword: '风险', skw_score: 0.2 },
        ],
      },
    })

    await expect(page.locator('.info-gap-btn')).toHaveCount(2)
    await page.locator('.info-gap-btn').filter({ hasText: '预算' }).click()
    await page.locator('.info-gap-btn').filter({ hasText: '风险' }).click()
    await expect(page.locator('.app-session-detail-info-gap-sticky')).toHaveCount(0)
  })

  test('info-gap click failure keeps the button visible for exception recovery', async ({ page }) => {
    await mockApis(page, {
      infoGapButtons: [{ id: 'fail-gap', keyword: '失败恢复', skw_score: 0.5 }],
      clickShouldFail: true,
    })
    await page.goto(`/app/sessions/${session.id}`)

    const btn = page.locator('.info-gap-btn').filter({ hasText: '失败恢复' })
    await btn.click()
    await expect(btn).toBeVisible()
  })

  test('malformed runtime payloads do not create empty AI cards or broken info-gap items', async ({ page }) => {
    await mockApis(page)
    await page.goto(`/app/sessions/${session.id}`)

    await emitWs(page, {
      type: 'push_notification',
      data: { content: '', target_user_id: user.id, triggered_at: '2026-03-01T10:00:09.000Z' },
    })
    await emitWs(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'bad-gap', keyword: '', skw_score: 0.1 }] },
    })

    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: /^$/ })).toHaveCount(0)
    await expect(page.locator('.info-gap-btn').filter({ hasText: /^$/ })).toHaveCount(0)
  })
})
