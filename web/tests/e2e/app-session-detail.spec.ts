import { test, expect } from '@playwright/test'

// 直接访问 /app/sessions/:id 会触发 fallback group 迭代，耗时较长
test.setTimeout(60000)

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

interface TestUser {
  email: string
  password: string
  userId: string
  token: string
}

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts = Date.now()
  const email = `app-sd-${label}-${ts}@example.com`
  const password = '1234'
  const name = `SD E2E ${label}`

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
  if (!res.ok) throw new Error(`开始会话失败: ${await res.text()}`)
}

async function addTranscriptViaAdmin(
  sessionId: string,
  groupId: string,
  speaker: string,
  text: string,
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/admin/transcripts/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
    body: JSON.stringify({
      session_id: sessionId,
      group_id: groupId,
      speaker,
      text,
      start: '2024-01-01T00:00:01.000Z',
      end: '2024-01-01T00:00:05.000Z',
    }),
  })
  if (!res.ok) throw new Error(`添加转写失败: ${await res.text()}`)
  const data = await res.json()
  return data.transcript_id as string
}

async function markPasswordResetByAdmin(userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/users/${userId}/mark-password-reset`, {
    method: 'POST',
    headers: { 'X-Admin-Token': ADMIN_API_KEY },
  })
  if (!res.ok) throw new Error(`标记改密失败: ${await res.text()}`)
}

async function loginViaUI(page: import('@playwright/test').Page, user: TestUser): Promise<void> {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

// ─────────────────────────────────────────────────────────────────────────────
// A. 基础加载
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppSessionDetail - 基础加载', () => {
  test('A-1: 直接访问 /app/sessions/:id，显示会话标题和状态', async ({ page }) => {
    const user = await registerAndLogin('a1')
    const groupId = await createGroup(user.token, `SD测试群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `A1测试会话-${Date.now()}`)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-title')).toBeVisible()
    await expect(page.locator('.app-session-detail-status-tag')).toBeVisible()
  })

  test('A-2: 点击返回按钮跳回 /app/sessions', async ({ page }) => {
    const user = await registerAndLogin('a2')
    const groupId = await createGroup(user.token, `SD返回测试群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `A2测试会话-${Date.now()}`)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await page.getByRole('button', { name: '← 返回会话列表' }).click()
    await expect(page).toHaveURL(/\/app\/sessions$/)
  })

  test('A-3: 从 AppSessions 点击「查看详情」进入详情页', async ({ page }) => {
    const user = await registerAndLogin('a3')
    const groupName = `SD入口测试群-${Date.now()}`
    const groupId = await createGroup(user.token, groupName)
    const sessionTitle = `A3入口测试会话-${Date.now()}`
    await createSession(user.token, groupId, sessionTitle)

    await loginViaUI(page, user)
    // 设置 app_current_group，确保 AppSessions 挂载时能自动拉取会话列表
    await page.evaluate(
      ({ id, name }) => { localStorage.setItem('app_current_group', JSON.stringify({ id, name })) },
      { id: groupId, name: groupName },
    )
    await page.goto('/app/sessions')
    await expect(page.locator('.app-sessions-item').first()).toBeVisible({ timeout: 15000 })

    await page.locator('.app-sessions-item').filter({ hasText: sessionTitle }).first()
      .getByRole('button', { name: '查看详情' }).click()

    await expect(page).toHaveURL(/\/app\/sessions\/.+/)
    await expect(page.locator('.app-session-detail-title')).toContainText(sessionTitle)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// B. 会话操作（serial，共用 fixture）
// ─────────────────────────────────────────────────────────────────────────────
test.describe.serial('AppSessionDetail - 会话操作', () => {
  let user: TestUser
  let groupId: string
  let sessionId: string

  test.beforeAll(async () => {
    user = await registerAndLogin('b-serial')
    groupId = await createGroup(user.token, `Serial操作群-${Date.now()}`)
    sessionId = await createSession(user.token, groupId, `Serial操作会话-${Date.now()}`)
  })

  test('B-1: 未开始状态显示「发起」和「取消会话」按钮', async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-status-tag')).toContainText('未开始')
    await expect(page.getByRole('button', { name: '发起' })).toBeVisible()
    await expect(page.getByRole('button', { name: '取消会话' })).toBeVisible()
  })

  test('B-2: 点击「发起」后状态变为进行中', async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await page.getByRole('button', { name: '发起' }).click()
    await expect(page.locator('.app-session-detail-status-tag')).toContainText('进行中')
    await expect(page.getByRole('button', { name: '发起' })).not.toBeVisible()
  })

  test('B-3: 点击「修改标题」弹出 prompt 并保存新标题', async ({ page }) => {
    const newTitle = `修改后标题-${Date.now()}`
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await page.getByRole('button', { name: '修改标题' }).click()
    // ElMessageBox.prompt 是 Element Plus DOM 组件，非原生 dialog
    await expect(page.locator('.el-message-box')).toBeVisible()
    await page.locator('.el-message-box__input input').fill(newTitle)
    await page.locator('.el-message-box').getByRole('button', { name: '保存' }).click()

    await expect(page.locator('.app-session-detail-title')).toContainText(newTitle)
  })

  test('B-4: 点击「结束」弹出确认后状态变为已结束', async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 会话已 ongoing（B-2 发起后），显示 ⏹ 结束 按钮
    await page.getByRole('button', { name: '结束' }).click()
    // ElMessageBox.confirm 是 Element Plus DOM 组件，scope 到 dialog 避免匹配到页面按钮
    await page.locator('.el-message-box').getByRole('button', { name: '结束' }).click()

    await expect(page.locator('.app-session-detail-status-tag')).toContainText('已结束')
  })

  test('B-5: 已结束状态下发起和结束按钮均不可见', async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 会话已结束，不再显示任何操作按钮
    await expect(page.getByRole('button', { name: '结束' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '发起' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '取消会话' })).not.toBeVisible()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// C. 转写展示
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppSessionDetail - 转写展示', () => {
  test('C-1: 无转写记录时显示「暂无转写记录」', async ({ page }) => {
    const user = await registerAndLogin('c1')
    const groupId = await createGroup(user.token, `C1无转写群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `C1无转写会话-${Date.now()}`)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-transcripts-empty')).toContainText('暂无转写记录')
  })

  test('C-2: 有转写记录时显示说话人和文本', async ({ page }) => {
    const user = await registerAndLogin('c2')
    const groupId = await createGroup(user.token, `C2有转写群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `C2有转写会话-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)
    await addTranscriptViaAdmin(sessionId, groupId, '张三', 'C2测试转写文本')

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-transcript-speaker').first()).toContainText('张三')
    await expect(page.locator('.app-session-detail-transcript-text').first()).toContainText('C2测试转写文本')
  })

  test('C-3: 多条转写记录均显示', async ({ page }) => {
    const user = await registerAndLogin('c3')
    const groupId = await createGroup(user.token, `C3多转写群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `C3多转写会话-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)
    await addTranscriptViaAdmin(sessionId, groupId, '说话人A', '第一句话')
    await addTranscriptViaAdmin(sessionId, groupId, '说话人B', '第二句话')

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-transcript-item')).toHaveCount(2)
  })

  test('C-4: speaker 为空时显示「未知说话人」', async ({ page }) => {
    const user = await registerAndLogin('c4')
    const groupId = await createGroup(user.token, `C4无speaker群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `C4无speaker会话-${Date.now()}`)
    await startSessionViaApi(user.token, sessionId)
    await addTranscriptViaAdmin(sessionId, groupId, '', '无说话人文本')

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page.locator('.app-session-detail-transcript-speaker').first()).toContainText('未知说话人')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// D. 边界 / 异常
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppSessionDetail - 边界异常', () => {
  test('D-1: 访问不存在的 session ID 显示错误', async ({ page }) => {
    const user = await registerAndLogin('d1')
    await loginViaUI(page, user)
    await page.goto('/app/sessions/00000000-0000-0000-0000-000000000000')

    await expect(page.locator('.app-session-detail-error')).toBeVisible()
  })

  test('D-2: 未登录访问详情页跳转到登录', async ({ page }) => {
    await page.goto('/app/sessions/any-session-id')
    await expect(page).toHaveURL(/\/app\/login/)
  })

  test('D-3: 取消「取消会话」确认弹窗，状态不变', async ({ page }) => {
    const user = await registerAndLogin('d3')
    const groupId = await createGroup(user.token, `D3取消结束群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `D3取消结束会话-${Date.now()}`)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // not_started 显示「取消会话」按钮；弹窗内的返回按钮文字为「返回」
    await page.getByRole('button', { name: '取消会话' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '返回' }).click()

    await expect(page.locator('.app-session-detail-status-tag')).toContainText('未开始')
  })

  test('D-4: 取消「修改标题」弹窗，标题不变', async ({ page }) => {
    const user = await registerAndLogin('d4')
    const originalTitle = `D4原标题-${Date.now()}`
    const groupId = await createGroup(user.token, `D4取消改名群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, originalTitle)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await page.getByRole('button', { name: '修改标题' }).click()
    await expect(page.locator('.el-message-box')).toBeVisible()
    await page.locator('.el-message-box').getByRole('button', { name: '取消' }).click()

    await expect(page.locator('.app-session-detail-title')).toContainText(originalTitle)
  })

  test('D-5: password_needs_reset 用户被重定向到改密页', async ({ page }) => {
    const user = await registerAndLogin('d5')
    const groupId = await createGroup(user.token, `D5改密群-${Date.now()}`)
    const sessionId = await createSession(user.token, groupId, `D5改密会话-${Date.now()}`)
    await markPasswordResetByAdmin(user.userId)

    // 手动设置 localStorage（loginViaUI 期望 /app，但 reset 用户会被重定向到改密页）
    await page.goto('/app/login')
    await page.evaluate(
      ({ token, userId, email }) => {
        localStorage.setItem('app_access_token', token)
        localStorage.setItem('app_user', JSON.stringify({ id: userId, email, name: email, password_needs_reset: true }))
      },
      { token: user.token, userId: user.userId, email: user.email },
    )
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(page).toHaveURL(/\/app\/change-password/)
  })
})
