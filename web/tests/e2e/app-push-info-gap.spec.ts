import { test, expect } from '@playwright/test'

test.setTimeout(60000)

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

// ── 测试工具 ──────────────────────────────────────────────────────────────────

interface TestUser {
  email: string
  password: string
  userId: string
  token: string
}

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts = Date.now()
  const email = `push-ig-${label}-${ts}@example.com`
  const password = '1234'
  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `PushIG ${label}`, email, password }),
  })
  if (!regRes.ok) throw new Error(`注册失败: ${await regRes.text()}`)
  const user = (await regRes.json()) as { id: string }
  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const loginData = (await loginRes.json()) as { access_token: string }
  return { email, password, userId: user.id, token: loginData.access_token }
}

async function createGroupAndSession(token: string, label: string): Promise<{ groupId: string; sessionId: string }> {
  const gRes = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name: `PushIG Group ${label} ${Date.now()}` }),
  })
  const groupId = (await gRes.json()).group.id as string
  const sRes = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ session_title: `PushIG Session ${label}` }),
  })
  const sessionId = (await sRes.json()).id as string
  await fetch(`${API_BASE}/api/sessions/${sessionId}/start`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  return { groupId, sessionId }
}

async function insertInfoGapButton(
  sessionId: string,
  userId: string,
  keyword: string,
  skwScore = 0.2,
): Promise<string> {
  // 通过后端 admin SQL 工具或直接调 DB 插入 — 这里用 admin 兜底接口
  // 实际跑测试时需要 DB 直连能力（见后端测试的 psycopg2 方案）
  // 此处通过 admin 创建 push_log 方式验证 UI 行为，info_gap_button 数据由 WebSocket mock 提供
  return `igb_mock_${Date.now()}`
}

async function loginViaUI(page: import('@playwright/test').Page, user: TestUser) {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

// ── 模拟 WebSocket 推送消息 ───────────────────────────────────────────────────

async function injectWsMessage(page: import('@playwright/test').Page, message: object) {
  await page.evaluate((msg) => {
    // 找到页面中存活的 WebSocket 实例并触发 onmessage
    const event = new MessageEvent('message', { data: JSON.stringify(msg) })
    // 通过 monkey-patch 方式注入
    ;(window as any).__lastWs?.dispatchEvent(event)
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

// ══════════════════════════════════════════════════════════════════════════════
// A. PushNotification 组件
// ══════════════════════════════════════════════════════════════════════════════

test.describe('PushNotification - 推送消息 Toast', () => {
  test('A-1: 收到 push_notification WS 消息 → Toast 显示推送内容', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('a1')
    const { sessionId } = await createGroupAndSession(user.token, 'a1')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'push_notification',
      data: { content: '大家可以深入讨论一下这个观点', target_user_id: user.userId },
    })

    await expect(page.locator('.push-notification')).toBeVisible({ timeout: 3000 })
    await expect(page.locator('.push-content')).toContainText('大家可以深入讨论一下这个观点')
  })

  test('A-2: Toast 在 3~5 秒后自动消失', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('a2')
    const { sessionId } = await createGroupAndSession(user.token, 'a2')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'push_notification',
      data: { content: '短暂提示', target_user_id: user.userId },
    })
    await expect(page.locator('.push-notification')).toBeVisible({ timeout: 3000 })
    // 等待 5.5s 后应该消失
    await page.waitForTimeout(5500)
    await expect(page.locator('.push-notification')).not.toBeVisible()
  })

  test('A-3: Toast 不遮挡操作（pointer-events: none）', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('a3')
    const { sessionId } = await createGroupAndSession(user.token, 'a3')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'push_notification',
      data: { content: '不阻断操作的提示', target_user_id: user.userId },
    })
    await expect(page.locator('.push-notification')).toBeVisible({ timeout: 3000 })

    const pointerEvents = await page.locator('.push-notification').evaluate(
      (el) => window.getComputedStyle(el).pointerEvents,
    )
    expect(pointerEvents).toBe('none')
  })

  test('A-4: 连续收到两条推送 → 第二条覆盖第一条重新计时', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('a4')
    const { sessionId } = await createGroupAndSession(user.token, 'a4')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'push_notification',
      data: { content: '第一条推送', target_user_id: user.userId },
    })
    await page.waitForTimeout(1000)
    await injectWsMessage(page, {
      type: 'push_notification',
      data: { content: '第二条推送', target_user_id: user.userId },
    })

    await expect(page.locator('.push-content')).toContainText('第二条推送', { timeout: 2000 })
  })

  test('A-5: content 为空字符串 → Toast 不显示（或显示但内容空）', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('a5')
    const { sessionId } = await createGroupAndSession(user.token, 'a5')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'push_notification',
      data: { content: '', target_user_id: user.userId },
    })
    // 空内容不应触发显示
    await page.waitForTimeout(500)
    const visible = await page.locator('.push-notification').isVisible()
    // 空 content 时 showPushNotification 不被调用（因为 if(d.content) 判断）
    expect(visible).toBe(false)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// B. InfoGapButtons 组件
// ══════════════════════════════════════════════════════════════════════════════

test.describe('InfoGapButtons - 信息缺口关键词按钮', () => {
  test('B-1: 收到 info_gap_button WS 消息 → 按钮显示在页面', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b1')
    const { sessionId } = await createGroupAndSession(user.token, 'b1')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: {
        buttons: [
          { id: 'btn_001', keyword: '机器学习', skw_score: 0.2 },
          { id: 'btn_002', keyword: '深度学习', skw_score: 0.15 },
        ],
      },
    })

    await expect(page.locator('.info-gap-btn').filter({ hasText: '机器学习' })).toBeVisible({ timeout: 3000 })
    await expect(page.locator('.info-gap-btn').filter({ hasText: '深度学习' })).toBeVisible()
  })

  test('B-2: 默认低透明度（静默浮现）', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b2')
    const { sessionId } = await createGroupAndSession(user.token, 'b2')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_003', keyword: '人工智能', skw_score: 0.2 }] },
    })

    await expect(page.locator('.info-gap-container')).toBeVisible({ timeout: 3000 })
    const opacity = await page.locator('.info-gap-container').evaluate(
      (el) => parseFloat(window.getComputedStyle(el).opacity),
    )
    expect(opacity).toBeLessThanOrEqual(0.65)
  })

  test('B-3: 点击按钮 → 按钮变灰且不可再点', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b3')
    const { sessionId } = await createGroupAndSession(user.token, 'b3')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    // mock API click endpoint
    await page.route(`**/api/sessions/${sessionId}/info-gap/click`, async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify({ success: true }) })
    })

    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_004', keyword: '可点击词', skw_score: 0.2 }] },
    })

    const btn = page.locator('.info-gap-btn').filter({ hasText: '可点击词' })
    await expect(btn).toBeVisible({ timeout: 3000 })
    await btn.click()

    // 点击后按钮应该变灰（--clicked class）
    await expect(btn).toHaveClass(/info-gap-btn--clicked/, { timeout: 3000 })
    await expect(btn).toBeDisabled()
  })

  test('B-4: 点击按钮发送正确的 POST 请求', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b4')
    const { sessionId } = await createGroupAndSession(user.token, 'b4')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    let capturedBody: Record<string, unknown> | null = null
    await page.route(`**/api/sessions/${sessionId}/info-gap/click`, async (route) => {
      capturedBody = JSON.parse(route.request().postData() ?? '{}')
      await route.fulfill({ status: 200, body: JSON.stringify({ success: true }) })
    })

    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_req_005', keyword: '请求验证', skw_score: 0.2 }] },
    })
    await page.locator('.info-gap-btn').filter({ hasText: '请求验证' }).click()
    await page.waitForTimeout(500)

    expect(capturedBody).not.toBeNull()
    expect(capturedBody!['button_id']).toBe('btn_req_005')
  })

  test('B-5: 点击失败（API 500）→ 按钮不变灰，静默处理', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b5')
    const { sessionId } = await createGroupAndSession(user.token, 'b5')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await page.route(`**/api/sessions/${sessionId}/info-gap/click`, async (route) => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_fail_006', keyword: '失败词', skw_score: 0.2 }] },
    })

    const btn = page.locator('.info-gap-btn').filter({ hasText: '失败词' })
    await expect(btn).toBeVisible({ timeout: 3000 })
    await btn.click()
    await page.waitForTimeout(800)

    // 失败后按钮不应该带 clicked class
    const classes = await btn.getAttribute('class')
    expect(classes).not.toContain('info-gap-btn--clicked')
  })

  test('B-6: 多次收到 info_gap_button → 去重合并，不重复显示', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b6')
    const { sessionId } = await createGroupAndSession(user.token, 'b6')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_dup_007', keyword: '重复词', skw_score: 0.2 }] },
    })
    await page.waitForTimeout(300)
    // 再推一次相同 id
    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_dup_007', keyword: '重复词', skw_score: 0.2 }] },
    })
    await page.waitForTimeout(300)

    const count = await page.locator('.info-gap-btn').filter({ hasText: '重复词' }).count()
    expect(count).toBe(1)
  })

  test('B-7: 会话结束后 InfoGapButtons 不显示', async ({ page }) => {
    await patchWsForCapture(page)
    const user = await registerAndLogin('b7')
    const { sessionId } = await createGroupAndSession(user.token, 'b7')
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(2000)

    // 先推按钮
    await injectWsMessage(page, {
      type: 'info_gap_button',
      data: { buttons: [{ id: 'btn_end_008', keyword: '结束后词', skw_score: 0.2 }] },
    })
    await expect(page.locator('.info-gap-btn').filter({ hasText: '结束后词' })).toBeVisible({ timeout: 3000 })

    // 会话结束
    await injectWsMessage(page, {
      type: 'session_ended',
      data: { session_id: sessionId, reason: 'host_ended' },
    })
    await page.waitForTimeout(500)

    // 会话 ended 后 v-if="session.status === 'ongoing'" 不满足，按钮区域应隐藏
    await expect(page.locator('.info-gap-container')).not.toBeVisible()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// C. GET info-gap/buttons API 集成
// ══════════════════════════════════════════════════════════════════════════════

test.describe('GET info-gap/buttons - API 集成', () => {
  test('C-1: 无 token → API 返回 401', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/sessions/s_fake/info-gap/buttons`)
    expect(res.status()).toBe(401)
  })

  test('C-2: 非成员 token → 403', async ({ request }) => {
    const user = await registerAndLogin('c2')
    const { sessionId } = await createGroupAndSession(user.token, 'c2')
    const outsider = await registerAndLogin('c2out')
    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/info-gap/buttons`, {
      headers: { Authorization: `Bearer ${outsider.token}` },
    })
    expect(res.status()).toBe(403)
  })

  test('C-3: 成员访问 → 200，返回数组', async ({ request }) => {
    const user = await registerAndLogin('c3')
    const { sessionId } = await createGroupAndSession(user.token, 'c3')
    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/info-gap/buttons`, {
      headers: { Authorization: `Bearer ${user.token}` },
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body)).toBe(true)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// D. GET summary API 集成
// ══════════════════════════════════════════════════════════════════════════════

test.describe('GET summary - API 集成', () => {
  test('D-1: 无摘要 → 404', async ({ request }) => {
    const user = await registerAndLogin('d1')
    const { sessionId } = await createGroupAndSession(user.token, 'd1')
    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/summary`, {
      headers: { Authorization: `Bearer ${user.token}` },
    })
    expect(res.status()).toBe(404)
  })

  test('D-2: 非成员 → 403', async ({ request }) => {
    const user = await registerAndLogin('d2')
    const { sessionId } = await createGroupAndSession(user.token, 'd2')
    const outsider = await registerAndLogin('d2out')
    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/summary`, {
      headers: { Authorization: `Bearer ${outsider.token}` },
    })
    expect(res.status()).toBe(403)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// E. GET window-metrics API 集成
// ══════════════════════════════════════════════════════════════════════════════

test.describe('GET window-metrics - API 集成', () => {
  test('E-1: 普通用户 → 403', async ({ request }) => {
    const user = await registerAndLogin('e1')
    const { sessionId } = await createGroupAndSession(user.token, 'e1')
    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/window-metrics`, {
      headers: { Authorization: `Bearer ${user.token}` },
    })
    expect(res.status()).toBe(403)
  })

  test('E-2: Admin token 无数据 → 404', async ({ request }) => {
    const user = await registerAndLogin('e2')
    const { sessionId } = await createGroupAndSession(user.token, 'e2')
    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/window-metrics`, {
      headers: { 'X-Admin-Token': ADMIN_API_KEY },
    })
    expect(res.status()).toBe(404)
  })

  test('E-3: 会话不存在 → 404', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/sessions/s_nonexistent/window-metrics`, {
      headers: { 'X-Admin-Token': ADMIN_API_KEY },
    })
    expect(res.status()).toBe(404)
  })
})
