import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

type ChatSessionItem = {
  id: string
  group_id: string
  session_title: string
  created_at: string
  last_updated: string
  is_active: boolean | null
  ended_at: string | null
}

async function loginAsAdminAndGoToChatSessions(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto('/admin/chat-sessions')
  await expect(page.getByRole('heading', { name: '会话管理' })).toBeVisible()
}

async function registerAndLogin(label: string): Promise<{ userId: string; accessToken: string }> {
  const email = `e2e-session-${label}-${Date.now()}@example.com`
  const password = 'Pass123!'

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: `会话测试-${label}`,
      email,
      password,
      device_token: `device-session-${label}`,
    }),
  })
  if (!regRes.ok) {
    throw new Error(`register failed: ${regRes.status} ${await regRes.text()}`)
  }
  const user = (await regRes.json()) as { id: string }

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) {
    throw new Error(`login failed: ${loginRes.status} ${await loginRes.text()}`)
  }
  const loginData = (await loginRes.json()) as { access_token: string }

  return { userId: user.id, accessToken: loginData.access_token }
}

async function createGroup(accessToken: string, name: string): Promise<{ groupId: string }> {
  const res = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) {
    throw new Error(`create group failed: ${res.status} ${await res.text()}`)
  }
  const data = await res.json()
  return { groupId: data.group.id as string }
}

async function createSession(accessToken: string, groupId: string, title: string): Promise<ChatSessionItem> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ session_title: title }),
  })
  if (!res.ok) {
    throw new Error(`create session failed: ${res.status} ${await res.text()}`)
  }
  const data = (await res.json()) as ChatSessionItem
  return data
}

async function endSession(accessToken: string, sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/end`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) {
    throw new Error(`end session failed: ${res.status} ${await res.text()}`)
  }
}

async function fetchAdminChatSessionsByGroup(groupId: string): Promise<ChatSessionItem[]> {
  const url = new URL('/api/admin/chat-sessions', API_BASE)
  url.searchParams.set('group_id', groupId)
  url.searchParams.set('page', '1')
  url.searchParams.set('page_size', '50')

  const res = await fetch(url, {
    headers: { 'X-Admin-Token': ADMIN_API_KEY },
  })
  if (!res.ok) {
    throw new Error(`admin list chat-sessions failed: ${res.status} ${await res.text()}`)
  }
  const data = (await res.json()) as { items: ChatSessionItem[] }
  return data.items
}

async function setupChatSessionsFixture() {
  const owner = await registerAndLogin('owner')
  const { groupId } = await createGroup(owner.accessToken, `会话管理测试群-${Date.now()}`)

  const s1 = await createSession(owner.accessToken, groupId, '第一次会话')
  const s2 = await createSession(owner.accessToken, groupId, '第二次会话')

  await endSession(owner.accessToken, s1.id)

  const sessions = await fetchAdminChatSessionsByGroup(groupId)
  const createdDates = sessions.map((s) => new Date(s.created_at)).filter((d) => !Number.isNaN(d.getTime()))

  const earliestCreatedAt = new Date(Math.min(...createdDates.map((d) => d.getTime())))
  const latestCreatedAt = new Date(Math.max(...createdDates.map((d) => d.getTime())))

  return {
    groupId,
    activeSessionTitle: '第二次会话',
    endedSessionTitle: '第一次会话',
    sessions,
    earliestCreatedAt,
    latestCreatedAt,
  }
}

const shared: {
  groupId: string
  activeSessionTitle: string
  endedSessionTitle: string
  sessions: ChatSessionItem[]
  earliestCreatedAt: Date
  latestCreatedAt: Date
} = {} as any

test.describe.serial('Admin 会话管理页面 - 查询与时间', () => {
  test.beforeAll(async () => {
    const fixture = await setupChatSessionsFixture()
    Object.assign(shared, fixture)
  })

  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToChatSessions(page)
  })

  test('1. 按群组 ID 查询出准备好的会话', async ({ page }) => {
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(rows.first()).toBeVisible()
  })

  test('2. 按会话标题模糊查询', async ({ page }) => {
    await page.getByPlaceholder('按会话标题模糊搜索').fill('第一次')
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.endedSessionTitle })
    await expect(rows.first()).toBeVisible()
  })

  test('3. 按状态筛选进行中 / 已结束', async ({ page }) => {
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)

    await page.locator('.admin-chat-sessions-filters .el-select').first().click()
    await page.getByRole('option', { name: '进行中' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const activeRows = page.getByRole('row').filter({ hasText: shared.activeSessionTitle })
    await expect(activeRows.first()).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    await page.locator('.admin-chat-sessions-filters .el-select').first().click()
    await page.getByRole('option', { name: '已结束' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const endedRows = page.getByRole('row').filter({ hasText: shared.endedSessionTitle })
    await expect(endedRows.first()).toBeVisible()
  })

  test('4. 按创建时间范围筛选（命中窗口）', async ({ page }) => {
    const start = new Date(shared.earliestCreatedAt.getTime() - 10 * 60 * 1000)
    const end = new Date(shared.latestCreatedAt.getTime() + 10 * 60 * 1000)
    const startStr = start.toISOString().slice(0, 19).replace('T', ' ')
    const endStr = end.toISOString().slice(0, 19).replace('T', ' ')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    const startInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('开始时间').first()
    const endInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('结束时间').first()
    await startInput.click()
    await startInput.fill(startStr)
    await endInput.fill(endStr)

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(rows.first()).toBeVisible()
  })

  test('5. 创建时间范围在未来查不到准备阶段会话', async ({ page }) => {
    const base = shared.latestCreatedAt
    const futureStart = new Date(base.getTime() + 60 * 60 * 1000)
    const futureEnd = new Date(base.getTime() + 2 * 60 * 60 * 1000)
    const startStr = futureStart.toISOString().slice(0, 19).replace('T', ' ')
    const endStr = futureEnd.toISOString().slice(0, 19).replace('T', ' ')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    const startInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('开始时间').first()
    const endInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('结束时间').first()
    await startInput.click()
    await startInput.fill(startStr)
    await endInput.fill(endStr)

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(rows).toHaveCount(0)
  })
})

test.describe('Admin 会话管理 - 查询组合与时间边界', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToChatSessions(page)
  })

  test('查询组合 - 群组 ID + 标题 + 状态', async ({ page }) => {
    const fixture = await setupChatSessionsFixture()

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)
    await page.getByPlaceholder('按会话标题模糊搜索').fill('第二次')
    await page.locator('.admin-chat-sessions-filters .el-select').first().click()
    await page.getByRole('option', { name: '进行中' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: '第二次会话' })
    await expect(rows.first()).toBeVisible()
  })

  test('创建时间仅设置开始或结束也能查到记录', async ({ page }) => {
    const fixture = await setupChatSessionsFixture()
    const createdDates = fixture.sessions
      .map((s) => new Date(s.created_at))
      .filter((d) => !Number.isNaN(d.getTime()))
    const earliest = new Date(Math.min(...createdDates.map((d) => d.getTime())))
    const latest = new Date(Math.max(...createdDates.map((d) => d.getTime())))

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)

    const startInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('开始时间').first()
    const endInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('结束时间').first()

    const fromOnly = new Date(earliest.getTime() - 5 * 60 * 1000)
    await startInput.click()
    await startInput.fill(fromOnly.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.clear()

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()
    const rowsFromOnly = page.getByRole('row').filter({ hasText: fixture.groupId })
    await expect(rowsFromOnly.first()).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)

    const toOnly = new Date(latest.getTime() + 5 * 60 * 1000)
    await endInput.click()
    await endInput.fill(toOnly.toISOString().slice(0, 19).replace('T', ' '))
    await startInput.clear()

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()
    const rowsToOnly = page.getByRole('row').filter({ hasText: fixture.groupId })
    await expect(rowsToOnly.first()).toBeVisible()
  })

  test('创建时间边界点（from=to=created_at）仍能查到记录', async ({ page }) => {
    const fixture = await setupChatSessionsFixture()
    const target = fixture.sessions[0]
    const createdAt = new Date(target.created_at)
    const boundary = createdAt.toISOString().slice(0, 19).replace('T', ' ')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)
    const startInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('开始时间').first()
    const endInput = page.locator('.admin-chat-sessions-filters').getByPlaceholder('结束时间').first()
    await startInput.click()
    await startInput.fill(boundary)
    await endInput.fill(boundary)

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: target.session_title })
    await expect(rows.first()).toBeVisible()
  })

  test('重置筛选 - 条件清空且列表恢复', async ({ page }) => {
    await page.getByPlaceholder('按群组 ID 精确查询').fill('不存在的群组')
    await page.getByPlaceholder('按会话标题模糊搜索').fill('不存在的标题')
    await page.getByRole('button', { name: '查询' }).click()

    await page.getByRole('button', { name: '重置' }).click()

    await expect(page.getByPlaceholder('按群组 ID 精确查询')).toHaveValue('')
    await expect(page.getByPlaceholder('按会话标题模糊搜索')).toHaveValue('')
  })
})

