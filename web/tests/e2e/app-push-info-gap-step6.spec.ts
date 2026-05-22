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
    sessionStatus?: 'ongoing' | 'ended'
    pushLogs?: unknown[]
    infoGapButtons?: unknown[]
    infoGapButtonsAll?: unknown[]
    transcripts?: unknown[]
    summary?: { content: string; version: number }
    summaries?: unknown[]
    clickShouldFail?: boolean
  } = {},
) {
  const sessionStatus = options.sessionStatus ?? 'ongoing'
  const pushLogs = options.pushLogs ?? []
  const infoGapButtons = options.infoGapButtons ?? []
  const infoGapButtonsAll = options.infoGapButtonsAll ?? infoGapButtons
  const summary = options.summary ?? { content: 'Push & InfoGap 测试摘要', version: 1 }
  const summaries = options.summaries ?? [
    {
      id: 'summary-v1',
      session_id: session.id,
      version: summary.version,
      content: summary.content,
      analysis_run_id: `summary:${session.id}:v${summary.version}`,
      window_start: '2026-03-01T10:00:00.000Z',
      window_end: '2026-03-01T10:05:00.000Z',
      created_at: '2026-03-01T10:05:00.000Z',
    },
  ]
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
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ ...session, status: sessionStatus }]),
    })
  })

  await page.route(`**/api/sessions/${session.id}/transcripts`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(transcripts) })
  })

  await page.route(`**/api/sessions/${session.id}/summary`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summary),
    })
  })

  await page.route(`**/api/sessions/${session.id}/summaries`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summaries),
    })
  })

  await page.route(`**/api/sessions/${session.id}/push-logs`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pushLogs) })
  })

  await page.route(`**/api/sessions/${session.id}/info-gap/buttons**`, async (route) => {
    const url = new URL(route.request().url())
    const body = url.searchParams.get('include_all') === 'true' ? infoGapButtonsAll : infoGapButtons
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })

  await page.route(`**/api/concepts/lookup`, async (route) => {
    if (options.clickShouldFail) {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'mock failure' }) })
      return
    }
    const body = JSON.parse(route.request().postData() ?? '{}') as { keyword?: string }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ keyword: body.keyword ?? '', content: 'mock概念解释' }),
    })
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
      type: 'group_notification',
      data: { content: '群体破冰消息', triggered_at: '2026-03-01T10:00:07.000Z' },
    })
    await emitWs(page, {
      type: 'push_notification',
      data: { content: '发给别人', target_user_id: 'other-user', triggered_at: '2026-03-01T10:00:08.000Z' },
    })

    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '发给当前用户' })).toBeVisible()
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '广播消息' })).toBeVisible()
    await expect(page.locator('.app-session-detail-ai-card').filter({ hasText: '群体破冰消息' })).toBeVisible()
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

  test('duplicate info-gap ids are de-duplicated and successful clicks leave viewed state', async ({ page }) => {
    await mockApis(page, {
      infoGapButtons: [{ id: 'seed-gap', keyword: '预算', skw_score: 0.1 }],
    })
    await page.goto(`/app/sessions/${session.id}`)

    await expect(page.locator('.ai-sheet')).toBeVisible()
    await emitWs(page, {
      type: 'info_gap_button',
      data: {
        buttons: [
          { id: 'seed-gap', keyword: '预算', skw_score: 0.1 },
          { id: 'new-gap', keyword: '风险', skw_score: 0.2 },
        ],
      },
    })

    // 先展开抽屉才能点击按钮
    await page.locator('.ai-sheet__handle-bar').click()
    await expect(page.locator('.info-gap-btn')).toHaveCount(2)
    await expect(page.locator('.info-gap-btn').first()).toContainText('风险')
    await page.locator('.info-gap-btn').filter({ hasText: '预算' }).click()
    await page.locator('.info-gap-btn').filter({ hasText: '风险' }).click()
    await expect(page.locator('.info-gap-btn')).toHaveCount(2)
    await expect(page.locator('.info-gap-btn--viewed')).toHaveCount(2)
  })

  test('info-gap click failure keeps the button visible for exception recovery', async ({ page }) => {
    await mockApis(page, {
      infoGapButtons: [{ id: 'fail-gap', keyword: '失败恢复', skw_score: 0.5 }],
      clickShouldFail: true,
    })
    await page.goto(`/app/sessions/${session.id}`)

    const btn = page.locator('.info-gap-btn').filter({ hasText: '失败恢复' })
    await page.locator('.ai-sheet__handle-bar').click()
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

  test('ai-sheet 默认收起，点击 handle 展开后显示摘要和关键词', async ({ page }) => {
    await mockApis(page, {
      infoGapButtons: [{ id: 'sheet-gap', keyword: '预算', skw_score: 0.1 }],
    })
    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)

    const sheet = page.locator('.ai-sheet')
    await expect(sheet).toBeVisible()

    // 默认收起：body 不可见
    await expect(page.locator('.ai-sheet__body')).not.toBeVisible()
    // 预览行有关键词文字
    await expect(page.locator('.ai-sheet__preview')).toContainText('预算')

    // 点击展开
    await page.locator('.ai-sheet__handle-bar').click()
    await expect(page.locator('.ai-sheet__body')).toBeVisible()
    await expect(page.locator('.ai-sheet__summary-section')).toContainText('Push & InfoGap 测试摘要')
    await expect(page.locator('.info-gap-btn').filter({ hasText: '预算' })).toBeVisible()
  })

  test('会话结束后 ai-sheet 保留并切换为只读概念展示', async ({ page }) => {
    await mockApis(page, {
      infoGapButtons: [{ id: 'end-gap', keyword: '结束词', skw_score: 0.1 }],
    })
    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)

    await emitWs(page, { type: 'session_ended', data: { session_id: session.id, reason: 'host_ended' } })
    await page.waitForTimeout(300)
    await expect(page.locator('.ai-sheet')).toBeVisible()
    await page.locator('.ai-sheet__handle-bar').click()
    await expect(page.locator('.info-gap-btn')).toHaveCount(0)
    await expect(page.locator('.ai-sheet__readonly-pill').filter({ hasText: '结束词' })).toBeVisible()
  })

  test('历史摘要在摘要卡内折叠展示，最新摘要保持主位', async ({ page }) => {
    await mockApis(page, {
      summary: { content: '当前最新摘要', version: 3 },
      summaries: [
        {
          id: 'summary-v3',
          session_id: session.id,
          version: 3,
          content: '当前最新摘要',
          analysis_run_id: 'summary-v3',
          window_start: '2026-03-01T10:20:00.000Z',
          window_end: '2026-03-01T10:30:00.000Z',
          created_at: '2026-03-01T10:30:00.000Z',
        },
        {
          id: 'summary-v2',
          session_id: session.id,
          version: 2,
          content: '上一轮摘要',
          analysis_run_id: 'summary-v2',
          window_start: '2026-03-01T10:10:00.000Z',
          window_end: '2026-03-01T10:20:00.000Z',
          created_at: '2026-03-01T10:20:00.000Z',
        },
        {
          id: 'summary-v1',
          session_id: session.id,
          version: 1,
          content: '更早摘要',
          analysis_run_id: 'summary-v1',
          window_start: '2026-03-01T10:00:00.000Z',
          window_end: '2026-03-01T10:10:00.000Z',
          created_at: '2026-03-01T10:10:00.000Z',
        },
      ],
    })
    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)

    await page.locator('.ai-sheet__handle-bar').click()
    await expect(page.locator('.ai-sheet__summary-section')).toContainText('当前最新摘要')
    await expect(page.locator('.ai-sheet__history-toggle')).toContainText('历史版本 (3)')
    await page.locator('.ai-sheet__history-toggle').click()
    await expect(page.locator('.ai-sheet__history-item')).toHaveCount(2)
    await expect(page.locator('.ai-sheet__history-item').first()).toContainText('v2')
    await expect(page.locator('.ai-sheet__history-item').first()).toContainText('上一轮摘要')
    await expect(page.locator('.ai-sheet__history-item').nth(1)).toContainText('v1')
  })

  test('ended 初始加载会带 include_all，保留已点击过的相关概念', async ({ page }) => {
    let includeAllSeen = false
    await mockApis(page, {
      sessionStatus: 'ended',
      infoGapButtons: [{ id: 'pending-gap', keyword: '未点击概念', skw_score: 0.1 }],
      infoGapButtonsAll: [
        { id: 'pending-gap', keyword: '未点击概念', skw_score: 0.1 },
        { id: 'clicked-gap', keyword: '已点击概念', skw_score: 0.3, status: 'clicked' },
      ],
    })
    await page.unroute(`**/api/sessions/${session.id}/info-gap/buttons**`)
    await page.route(`**/api/sessions/${session.id}/info-gap/buttons**`, async (route) => {
      const url = new URL(route.request().url())
      includeAllSeen = url.searchParams.get('include_all') === 'true'
      const body = includeAllSeen
        ? [
            { id: 'pending-gap', keyword: '未点击概念', skw_score: 0.1 },
            { id: 'clicked-gap', keyword: '已点击概念', skw_score: 0.3, status: 'clicked' },
          ]
        : [{ id: 'pending-gap', keyword: '未点击概念', skw_score: 0.1 }]
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    })

    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)
    await page.locator('.ai-sheet__handle-bar').click()

    expect(includeAllSeen).toBe(true)
    await expect(page.locator('.ai-sheet__readonly-pill').filter({ hasText: '未点击概念' })).toBeVisible()
    await expect(page.locator('.ai-sheet__readonly-pill').filter({ hasText: '已点击概念' })).toBeVisible()
  })

  test('收到新 info_gap_button WS 推送，预览行实时更新', async ({ page }) => {
    await mockApis(page)
    await page.goto(`/app/sessions/${session.id}`)
    await waitForDetailReady(page)

    await emitWs(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'live-gap', keyword: '实时词', skw_score: 0.2 }] },
    })

    await expect(page.locator('.ai-sheet')).toBeVisible({ timeout: 3000 })
    await expect(page.locator('.ai-sheet__preview')).toContainText('实时词')
  })
})
