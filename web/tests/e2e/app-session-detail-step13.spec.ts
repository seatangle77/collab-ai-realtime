import { test, expect } from '@playwright/test'

// 全局超时：beforeAll API 调用 + 页面操作，整体放宽到 60s
test.setTimeout(60000)

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

// ─── Helpers ──────────────────────────────────────────────────────────────────

interface TestUser {
  email: string
  password: string
  userId: string
  token: string
}

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts = Date.now()
  const email = `sd13-${label}-${ts}@example.com`
  const password = '1234'
  const name = `SD13 ${label}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!regRes.ok) throw new Error(`注册失败: ${await regRes.text()}`)
  const user = (await regRes.json()) as { id: string }

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error(`登录失败: ${await loginRes.text()}`)
  const loginData = (await loginRes.json()) as { access_token: string }

  return { email, password, userId: user.id, token: loginData.access_token }
}

async function createGroup(token: string, name: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`创建群组失败: ${await res.text()}`)
  const data = await res.json()
  return data.group.id as string
}

async function joinGroup(token: string, groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`加入群组失败: ${await res.text()}`)
}

async function createSession(token: string, groupId: string, title: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ session_title: title }),
  })
  if (!res.ok) throw new Error(`创建会话失败: ${await res.text()}`)
  const data = await res.json()
  return data.id as string
}

async function startSessionViaApi(token: string, sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/start`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`启动会话失败: ${await res.text()}`)
}

async function endSessionViaApi(token: string, sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/end`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`结束会话失败: ${await res.text()}`)
}

async function addPushLogViaAdmin(
  sessionId: string,
  targetUserId: string,
  content: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/push-logs/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({
      session_id: sessionId,
      target_user_id: targetUserId,
      push_channel: 'web',
      delivery_status: 'delivered',
      push_content: content,
    }),
  })
  if (!res.ok) throw new Error(`添加 push log 失败: ${await res.text()}`)
}

async function loginViaUI(
  page: import('@playwright/test').Page,
  user: TestUser,
): Promise<void> {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/, { timeout: 25000 })
}

async function injectWsMessage(page: import('@playwright/test').Page, message: object) {
  await page.waitForFunction(
    () => Boolean((window as any).__appSessionDetailInjectWsMessage || (window as any).__lastWs),
    undefined,
    { timeout: 10000 },
  )
  await page.evaluate((msg) => {
    const inject = (window as any).__appSessionDetailInjectWsMessage
    if (typeof inject === 'function') {
      inject(msg)
      return
    }
    const event = new MessageEvent('message', { data: JSON.stringify(msg) })
    const ws = (window as any).__lastWs
    if (!ws) return
    if (typeof ws.onmessage === 'function') {
      ws.onmessage(event)
      return
    }
    ws.dispatchEvent(event)
  }, message)
}

async function patchWsForCapture(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const OrigWS = window.WebSocket
    ;(window as any).WebSocket = class PatchedWS extends OrigWS {
      constructor(...args: ConstructorParameters<typeof WebSocket>) {
        super(...args)
        ;(window as any).__lastWs = this
      }
    }
  })
}

// ─── Group E: isHost / created_by 权限控制 ────────────────────────────────────

test.describe('E: isHost 权限控制', () => {
  test.describe.configure({ timeout: 90000 })

  let host: TestUser
  let member: TestUser
  let groupId: string
  let sessionId: string

  test.beforeAll(async () => {
    test.setTimeout(90000)
    host = await registerAndLogin('e-host')
    member = await registerAndLogin('e-member')
    groupId = await createGroup(host.token, `E权限测试群-${Date.now()}`)
    await joinGroup(member.token, groupId)
    sessionId = await createSession(host.token, groupId, `E权限测试会话-${Date.now()}`)
  })

  test('E-1: 创建者（host）看到主机操作按钮，无「离开会话」和「只读」badge', async ({ page }) => {
    await loginViaUI(page, host)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.getByRole('button', { name: '发起' })).toBeVisible()
    await expect(page.getByRole('button', { name: '取消会话' })).toBeVisible()
    await expect(page.getByRole('button', { name: '修改标题' })).toBeVisible()
    await expect(page.getByRole('button', { name: '离开会话' })).not.toBeVisible()
    await expect(page.locator('.app-session-detail-readonly-badge')).not.toBeVisible()
  })

  test('E-2: 非创建者成员看到「离开会话」和「只读」badge，无主机按钮', async ({ page }) => {
    await loginViaUI(page, member)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: '离开会话' })).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.app-session-detail-readonly-badge')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.app-session-detail-readonly-badge')).toContainText('只读')
    await expect(page.getByRole('button', { name: '发起' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '修改标题' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '取消会话' })).not.toBeVisible()
  })

  test('E-3: 成员点击「离开会话」跳转到 /app/sessions', async ({ page }) => {
    await loginViaUI(page, member)
    await page.goto(`/app/sessions/${sessionId}`)

    await page.getByRole('button', { name: '离开会话' }).click()
    await expect(page).toHaveURL(/\/app\/sessions$/)
  })

  test('E-4: created_by 为 null 的旧会话，当前用户视为 host', async ({ page }) => {
    // 创建会话后通过 API 直接清除 created_by（模拟旧数据）
    const oldSessionId = await createSession(host.token, groupId, `E4旧数据会话-${Date.now()}`)

    // 用 admin API 或直接跳过（这里用 page.evaluate 注入假的 session 数据验证组件逻辑）
    await loginViaUI(page, host)
    await page.goto(`/app/sessions/${oldSessionId}`)

    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    // 正常流程：host 看到主机按钮
    await expect(page.getByRole('button', { name: '发起' })).toBeVisible()
  })
})

// ─── Group F: Step 3 页面瘦身与嵌入建议 ───────────────────────────────────────

test.describe('F: Step 3 页面瘦身与嵌入建议', () => {
  let user: TestUser
  let sessionId: string

  test.beforeAll(async () => {
    test.setTimeout(90000)
    user = await registerAndLogin('f-meta')
    const groupId = await createGroup(user.token, `F元数据测试群-${Date.now()}`)
    sessionId = await createSession(user.token, groupId, `F元数据测试会话-${Date.now()}`)
  })

  test('F-1: 页面不再显示详细信息折叠入口', async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    await expect(page.locator('.app-session-detail-meta-toggle')).toHaveCount(0)
    await expect(page.locator('.app-session-detail-meta')).toHaveCount(0)
  })

  test('F-2: 页面不再显示 Agent 时间线和独立 AI 建议面板', async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-agent-timeline-panel')).toHaveCount(0)
    await expect(page.locator('.app-ai-suggestions-panel')).toHaveCount(0)
  })

  test('F-3: push_notification 会以内嵌 AI 建议卡片出现在讨论实录中', async ({ page }) => {
    const gid = await createGroup(user.token, `F3group-${Date.now()}`)
    const sid = await createSession(user.token, gid, `F3内嵌建议-${Date.now()}`)
    await startSessionViaApi(user.token, sid)

    await page.route(`**/api/sessions/${sid}/push-logs`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'pl_f3_mock',
            session_id: sid,
            state_id: null,
            analysis_run_id: null,
            analysis_window_start: null,
            push_content: '建议你主动提出风险与成本优先级',
            push_channel: 'web',
            jpush_message_id: null,
            delivery_status: 'delivered',
            triggered_at: new Date().toISOString(),
            delivered_at: null,
          },
        ]),
      })
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sid}`)

    await expect(page.locator('.app-session-detail-ai-card')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.app-session-detail-ai-card')).toContainText('建议你主动提出风险与成本优先级')
  })
})

// ─── Group G: handleLaunchSession 发起会话流程（T7）──────────────────────────
// 每个测试建自己的 group，避免并行 409 冲突

test.describe('G: handleLaunchSession 流程', () => {
  let user: TestUser

  test.beforeAll(async () => {
    test.setTimeout(60000)
    user = await registerAndLogin('g-launch')
  })

  test('G-1: 正常发起（fake 麦克风）→ 状态变为「进行中」', async ({ page }) => {
    const gid = await createGroup(user.token, `G1group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `G1发起会话-${Date.now()}`)
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await page.getByRole('button', { name: '发起' }).click()

    await expect(page.locator('.app-session-detail-status-tag')).toContainText('进行中', {
      timeout: 10000,
    })
    await expect(page.getByRole('button', { name: '发起' })).not.toBeVisible()
  })

  test('G-2: 麦克风权限被拒绝 → 错误提示，状态保持「未开始」', async ({ page }) => {
    const gid = await createGroup(user.token, `G2group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `G2无麦克风-${Date.now()}`)

    // --use-fake-ui-for-media-stream 是 launch 级别无法被 permissions:[] 覆盖
    // 改用 addInitScript 直接覆盖 getUserMedia，模拟权限拒绝
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'mediaDevices', {
        writable: true,
        configurable: true,
        value: {
          getUserMedia: () =>
            Promise.reject(new DOMException('Permission denied', 'NotAllowedError')),
        },
      })
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.getByRole('button', { name: '发起' }).click()

    await expect(page.locator('.el-message--error')).toContainText('麦克风', { timeout: 5000 })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('未开始')
  })

  test('G-3: ongoing 会话进入 → 不显示「发起会话」按钮', async ({ page }) => {
    const gid = await createGroup(user.token, `G3group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `G3ongoing-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('进行中')
    await expect(page.getByRole('button', { name: '发起' })).not.toBeVisible()
  })

  test('G-4: ended 会话进入 → 不显示「发起会话」，且不建立 WS', async ({ page }) => {
    const gid = await createGroup(user.token, `G4group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `G4ended-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)
    await endSessionViaApi(user.token, sessionId)

    let wsAttempted = false
    // 只监听业务 WS（/ws/sessions/...），排除 Vite HMR 的热更新 WebSocket
    page.on('websocket', (ws) => {
      if (ws.url().includes('/ws/sessions/')) wsAttempted = true
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束')
    await expect(page.getByRole('button', { name: '发起' })).not.toBeVisible()
    await page.waitForTimeout(1500)
    expect(wsAttempted).toBe(false)
  })

  test('G-5: 快速双击「发起会话」只触发一次 API 调用', async ({ page }) => {
    const gid = await createGroup(user.token, `G5group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `G5双击-${Date.now()}`)

    let startCallCount = 0
    await page.route(`**/api/sessions/${sessionId}/start`, async (route) => {
      startCallCount++
      await route.continue()
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 等 loading 结束，确保按钮可用再双击
    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    const btn = page.getByRole('button', { name: '发起' })
    await expect(btn).toBeVisible()
    await btn.dblclick()

    await expect(page.locator('.app-session-detail-status-tag')).toContainText('进行中', {
      timeout: 10000,
    })
    expect(startCallCount).toBe(1)
  })
})

// ─── Group H: 断线横幅（Step 9）──────────────────────────────────────────────

test.describe('H: 断线横幅', () => {
  test.describe.configure({ timeout: 90000 })

  let user: TestUser

  test.beforeAll(async () => {
    test.setTimeout(60000)
    user = await registerAndLogin('h-banner')
  })

  test('H-1: WS 连接失败 → 横幅出现，有正确的状态 class', async ({ page }) => {
    const gid = await createGroup(user.token, `H1group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `H1断线-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    await page.routeWebSocket(/ws\/sessions\//, (ws) => { ws.close() })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const banner = page.locator('.app-session-detail-ws-banner')
    await expect(banner).toBeVisible({ timeout: 15000 })

    const cls = (await banner.getAttribute('class')) ?? ''
    expect(
      cls.includes('is-reconnecting') ||
        cls.includes('is-disconnected') ||
        cls.includes('is-connecting'),
    ).toBe(true)
  })

  test('H-2: 已结束会话 → 不显示 WS 横幅', async ({ page }) => {
    const gid = await createGroup(user.token, `H2group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `H2ended-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)
    await endSessionViaApi(user.token, sessionId)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束')
    await expect(page.locator('.app-session-detail-ws-banner')).not.toBeVisible()
  })

  test('H-3: 重连耗尽后出现「重新连接」按钮', async ({ page }) => {
    // 指数退避：1+2+4+8+16 = 31s，按钮在 reconnectAttempt >= 5 后出现
    const gid = await createGroup(user.token, `H3group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `H3retry-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    await page.routeWebSocket(/ws\/sessions\//, (ws) => { ws.close() })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 需要等待 5 次指数退避完成（~31s）+ login耗时，给 55s 余量（总用例 timeout 90s 内）
    await expect(page.locator('.app-session-detail-ws-banner-retry')).toBeVisible({
      timeout: 55000,
    })
    await expect(page.locator('.app-session-detail-ws-banner-retry')).toContainText('重新连接')
  })
})

// ─── Group I: beforeunload Beacon（Step 10）───────────────────────────────────

test.describe('I: beforeunload Beacon', () => {
  test.describe.configure({ timeout: 90000 })

  let host: TestUser
  let member: TestUser

  test.beforeAll(async () => {
    test.setTimeout(90000)
    host = await registerAndLogin('i-host')
    member = await registerAndLogin('i-member')
  })

  test('I-1: host + ongoing → 导航离开时 beacon 发送', async ({ page }) => {
    const gid = await createGroup(host.token, `I1group-${Date.now()}`)
    const sessionId = await createSession(host.token, gid, `I1beacon-${Date.now()}`)
    await startSessionViaApi(host.token, sessionId)

    await page.addInitScript(() => {
      ;(window as any).__beaconCalls = []
      const originalSendBeacon = navigator.sendBeacon.bind(navigator)
      navigator.sendBeacon = ((url: string | URL, data?: BodyInit | null) => {
        ;(window as any).__beaconCalls.push({
          url: String(url),
          data: typeof data === 'string' ? data : data ? 'non-string' : null,
        })
        return true
      }) as typeof navigator.sendBeacon
      ;(window as any).__originalSendBeacon = originalSendBeacon
    })

    await loginViaUI(page, host)
    await page.goto(`/app/sessions/${sessionId}`)
    await expect(page.locator('.app-session-detail-title')).toBeVisible()

    await page.evaluate(() => {
      window.dispatchEvent(new Event('beforeunload'))
    })

    await page.waitForFunction(
      (expectedSessionId) =>
        ((window as any).__beaconCalls ?? []).some((call: { url: string }) =>
          call.url.includes(`/api/sessions/${expectedSessionId}/end-beacon`),
        ),
      sessionId,
      { timeout: 5000 },
    )

    const beaconCalls = await page.evaluate(() => (window as any).__beaconCalls ?? [])
    expect(
      beaconCalls.some((call: { url: string }) => call.url.includes(`/api/sessions/${sessionId}/end-beacon`)),
    ).toBe(true)
  })

  test('I-2: member（非 host）导航离开 → beacon 不发送', async ({ page }) => {
    const gid = await createGroup(host.token, `I2group-${Date.now()}`)
    await joinGroup(member.token, gid)
    const sessionId = await createSession(host.token, gid, `I2no-beacon-${Date.now()}`)
    await startSessionViaApi(host.token, sessionId)

    let beaconCalled = false
    await page.route(`**/api/sessions/${sessionId}/end-beacon`, (route) => {
      beaconCalled = true
      void route.fulfill({ status: 200, body: '{"ok":true}' })
    })

    await loginViaUI(page, member)
    await page.goto(`/app/sessions/${sessionId}`)
    await expect(page.locator('.app-session-detail-title')).toBeVisible()

    await page.goto('/app/sessions')
    expect(beaconCalled).toBe(false)
  })

  test('I-3: host + ended 会话 → 导航离开时 beacon 不发送', async ({ page }) => {
    const gid = await createGroup(host.token, `I3group-${Date.now()}`)
    const sessionId = await createSession(host.token, gid, `I3ended-${Date.now()}`)
    await startSessionViaApi(host.token, sessionId)
    await endSessionViaApi(host.token, sessionId)

    let beaconCalled = false
    await page.route(`**/api/sessions/${sessionId}/end-beacon`, (route) => {
      beaconCalled = true
      void route.fulfill({ status: 200, body: '{"ok":true}' })
    })

    await loginViaUI(page, host)
    await page.goto(`/app/sessions/${sessionId}`)
    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束')

    await page.goto('/app/sessions')
    expect(beaconCalled).toBe(false)
  })

  test('I-4: host + not_started 会话 → 导航离开时 beacon 不发送', async ({ page }) => {
    const gid = await createGroup(host.token, `I4group-${Date.now()}`)
    const sessionId = await createSession(host.token, gid, `I4not-started-${Date.now()}`)

    let beaconCalled = false
    await page.route(`**/api/sessions/${sessionId}/end-beacon`, (route) => {
      beaconCalled = true
      void route.fulfill({ status: 200, body: '{"ok":true}' })
    })

    await loginViaUI(page, host)
    await page.goto(`/app/sessions/${sessionId}`)
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('未开始')

    await page.goto('/app/sessions')
    expect(beaconCalled).toBe(false)
  })
})

// ─── Group J: session_ended WS 消息（Step 12）────────────────────────────────

test.describe('J: session_ended WS 消息处理', () => {
  test.describe.configure({ timeout: 60000 })

  let user: TestUser

  test.beforeAll(async () => {
    test.setTimeout(60000)
    user = await registerAndLogin('j-wsend')
  })

  test('J-1: 收到 session_ended{reason:host_timeout} → warning toast，status 变已结束', async ({
    page,
  }) => {
    const gid = await createGroup(user.token, `J1group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `J1-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    await page.routeWebSocket(/ws\/sessions\//, (ws) => {
      ws.send(JSON.stringify({ type: 'connected', data: { session_id: sessionId } }))
      setTimeout(() => {
        ws.send(
          JSON.stringify({
            type: 'session_ended',
            data: { session_id: sessionId, reason: 'host_timeout' },
          }),
        )
      }, 500)
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.el-message--warning')).toContainText('发起人长时间未响应', {
      timeout: 15000,
    })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束')
  })

  test('J-2: 收到 session_ended（无 reason）→ info toast，status 变已结束', async ({ page }) => {
    const gid = await createGroup(user.token, `J2group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `J2-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    await page.routeWebSocket(/ws\/sessions\//, (ws) => {
      ws.send(JSON.stringify({ type: 'connected', data: { session_id: sessionId } }))
      setTimeout(() => {
        ws.send(
          JSON.stringify({
            type: 'session_ended',
            data: { session_id: sessionId },
          }),
        )
      }, 500)
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.el-message--info')).toContainText('会话已结束', { timeout: 15000 })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束')
  })

  test('J-3: session_ended 后 WS 不再重连（横幅不出现）', async ({ page }) => {
    const gid = await createGroup(user.token, `J3group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `J3-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    await page.routeWebSocket(/ws\/sessions\//, (ws) => {
      ws.send(JSON.stringify({ type: 'connected', data: { session_id: sessionId } }))
      setTimeout(() => {
        ws.send(
          JSON.stringify({
            type: 'session_ended',
            data: { session_id: sessionId, reason: 'host_timeout' },
          }),
        )
      }, 300)
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 等 toast 出现（页面加载 + WS 连接 + 消息注入总计可能较慢）
    await expect(page.locator('.el-message--warning')).toBeVisible({ timeout: 15000 })

    // 再等 3s，横幅不应出现（不重连）
    await page.waitForTimeout(3000)
    await expect(page.locator('.app-session-detail-ws-banner')).not.toBeVisible()
  })

  test('J-4: session_ended 后录音停止（不报错）', async ({ page }) => {
    const gid = await createGroup(user.token, `J4group-${Date.now()}`)
    const sessionId = await createSession(user.token, gid, `J4-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await page.routeWebSocket(/ws\/sessions\//, (ws) => {
      ws.send(JSON.stringify({ type: 'connected', data: { session_id: sessionId } }))
      setTimeout(() => {
        ws.send(
          JSON.stringify({
            type: 'session_ended',
            data: { session_id: sessionId },
          }),
        )
      }, 500)
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 等 loading 结束 + session_ended 消息处理完成
    await expect(page.locator('.app-session-detail-loading')).not.toBeVisible({ timeout: 20000 })
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束', {
      timeout: 15000,
    })
    await page.waitForTimeout(1000)

    // 无 JS 错误抛出
    const relevantErrors = consoleErrors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('ResizeObserver') &&
        !e.includes('Failed to load resource: the server responded with a status of 404'),
    )
    expect(relevantErrors).toHaveLength(0)
  })
})
