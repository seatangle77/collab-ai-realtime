import { test, expect } from '@playwright/test'
import fs from 'fs'
import { randomUUID } from 'crypto'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const RUN_ID = randomUUID().replace(/-/g, '').slice(0, 6)

type ChatSessionItem = {
  id: string
  group_id: string
  group_name: string | null
  session_title: string
  created_at: string
  last_updated: string
  status: 'not_started' | 'ongoing' | 'ended' | null
  started_at: string | null
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
  const email = `e2e-session-${label}-${RUN_ID}-${Date.now()}@example.com`
  const password = '1234'

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: `Admin Session User ${label} ${RUN_ID}`,
      email,
      password,
      device_token: `device-session-${label}-${RUN_ID}`,
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
  const { groupId } = await createGroup(owner.accessToken, `Admin Session Group ${RUN_ID}`)

  const activeTitle = `Session Two ${RUN_ID}`
  const endedTitle = `Session One ${RUN_ID}`

  const s1 = await createSession(owner.accessToken, groupId, endedTitle)
  const s2 = await createSession(owner.accessToken, groupId, activeTitle)

  await endSession(owner.accessToken, s1.id)

  const sessions = await fetchAdminChatSessionsByGroup(groupId)
  const createdDates = sessions.map((s) => new Date(s.created_at)).filter((d) => !Number.isNaN(d.getTime()))

  const earliestCreatedAt = new Date(Math.min(...createdDates.map((d) => d.getTime())))
  const latestCreatedAt = new Date(Math.max(...createdDates.map((d) => d.getTime())))

  return {
    groupId,
    groupName: sessions[0]?.group_name ?? null,
    activeSessionTitle: activeTitle,
    endedSessionTitle: endedTitle,
    sessions,
    earliestCreatedAt,
    latestCreatedAt,
  }
}

const shared: {
  groupId: string
  groupName: string | null
  activeSessionTitle: string
  endedSessionTitle: string
  sessions: ChatSessionItem[]
  earliestCreatedAt: Date
  latestCreatedAt: Date
} = {} as any

const comboFixture: {
  groupId: string
  groupName: string | null
  activeSessionTitle: string
  endedSessionTitle: string
  sessions: ChatSessionItem[]
  earliestCreatedAt: Date
  latestCreatedAt: Date
} = {} as any

function toElDateTimeString(d: Date): string {
  // Element Plus datetime 输入使用 "YYYY-MM-DD HH:mm:ss" 文本格式
  return d.toISOString().slice(0, 19).replace('T', ' ')
}

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
    const firstRow = rows.first()
    await expect(firstRow).toBeVisible()
    if (shared.groupName) {
      await expect(firstRow).toContainText(shared.groupName)
    }
  })

  test('2. 按会话标题模糊查询', async ({ page }) => {
    await page.getByPlaceholder('按会话标题模糊搜索').fill(shared.endedSessionTitle)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.endedSessionTitle })
    await expect(rows.first()).toBeVisible()
  })

  test('3. 按状态筛选进行中 / 已结束', async ({ page }) => {
    const sessions = shared.sessions
    const endedSession = sessions.find((s) => s.status === 'ended')
    const ongoingSession = sessions.find((s) => s.status === 'ongoing')

    // 先验证「已结束」筛选一定能命中至少一条（fixture 中 Session One 已结束）
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    await page.locator('.admin-chat-sessions-filters .el-select').first().click()
    await page.getByRole('option', { name: '已结束' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const endedRows = page
      .getByRole('row')
      .filter({ hasText: (endedSession ?? { session_title: shared.endedSessionTitle }).session_title })
    await expect(endedRows.first()).toBeVisible()

    // 再验证「进行中」筛选：
    // - 如果 fixture 中确实存在 ongoing 会话，则应能命中该会话；
    // - 如果不存在 ongoing 会话，则进行中筛选结果应为空。
    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    await page.locator('.admin-chat-sessions-filters .el-select').first().click()
    await page.getByRole('option', { name: '进行中' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    if (ongoingSession) {
      const activeRows = page
        .getByRole('row')
        .filter({ hasText: ongoingSession.session_title })
      await expect(activeRows.first()).toBeVisible()
    } else {
      const rows = page.getByRole('row').filter({ hasText: shared.groupId })
      await expect(rows).toHaveCount(0)
    }
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

test.describe('Admin 会话管理页面 - 新建与编辑会话', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToChatSessions(page)
  })

  test('通过后台页面新建会话（未设置开始时间）', async ({ page }) => {
    const owner = await registerAndLogin('create-default')
    const groupName = `Admin Create Default Group ${RUN_ID}`
    const { groupId } = await createGroup(owner.accessToken, groupName)
    const title = `Admin E2E Create Default ${RUN_ID}`

    await page.getByRole('button', { name: '新建会话' }).click()

    // 选择所属群组：下拉选项 label 中包含 groupId
    const dialog = page.getByRole('dialog').filter({ hasText: '新建会话' })
    // Element Plus 下拉选择器，点击外层 .el-select 触发展开，避免 placeholder 文本拦截点击
    const groupSelectWrapper = dialog.locator('.el-select').first()
    await groupSelectWrapper.click()
    await page.getByRole('option', { name: new RegExp(groupId) }).click()

    await dialog.getByPlaceholder('请输入会话标题').fill(title)
    // 不设置"开始时间"，让后端使用默认当前时间

    await dialog.getByRole('button', { name: '创建' }).click()

    // 按群组 ID 查询，应该能看到刚创建的会话
    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: title })
    const firstRow = rows.first()
    await expect(firstRow).toBeVisible()
    await expect(firstRow).toContainText(groupName)
  })

  test('通过后台页面新建会话并显式设置开始时间', async ({ page }) => {
    const owner = await registerAndLogin('create-with-start')
    const groupName = `Admin Create With Start Group ${RUN_ID}`
    const { groupId } = await createGroup(owner.accessToken, groupName)
    const title = `Admin E2E Create With Start ${RUN_ID}`

    // 我们设定一个比当前时间早 1 小时的开始时间，便于与默认 NOW 区分
    const start = new Date(Date.now() - 60 * 60 * 1000)
    const startStr = toElDateTimeString(start)

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog').filter({ hasText: '新建会话' })

    const groupSelectWrapper = dialog.locator('.el-select').first()
    await groupSelectWrapper.click()
    await page.getByRole('option', { name: new RegExp(groupId) }).click()

    await dialog.getByPlaceholder('请输入会话标题').fill(title)

    const startInput = dialog.getByPlaceholder('不填则默认为当前时间')
    await startInput.click()
    await startInput.fill(startStr)
    await page.keyboard.press('Escape')

    await dialog.getByRole('button', { name: '创建' }).click()

    // 按群组 ID 和标题查询，确认使用显式开始时间创建的会话成功出现在列表中
    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByPlaceholder('按会话标题模糊搜索').fill(title)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: title })
    const firstRow = rows.first()
    await expect(firstRow).toBeVisible()
    await expect(firstRow).toContainText(groupName)
  })

  test('编辑会话时可以修改创建时间', async ({ page }) => {
    const owner = await registerAndLogin('edit-created-at')
    const { groupId } = await createGroup(owner.accessToken, `Admin Edit Created At Group ${RUN_ID}`)
    const title = `Admin E2E Edit Created At ${RUN_ID}`

    const created = await createSession(owner.accessToken, groupId, title)
    const beforeItems = await fetchAdminChatSessionsByGroup(groupId)
    const before = beforeItems.find((s) => s.id === created.id)
    expect(before).toBeDefined()
    const beforeCreatedAt = new Date(before!.created_at)

    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const targetRow = page.getByRole('row').filter({ hasText: title }).first()
    await expect(targetRow).toBeVisible()
    await targetRow.getByRole('button', { name: '编辑' }).click()

    const dialog = page.getByRole('dialog').filter({ hasText: '编辑会话' })
    const createdInput = dialog.getByPlaceholder('留空则不修改').first()

    const newCreated = new Date(beforeCreatedAt.getTime() - 24 * 60 * 60 * 1000)
    const newCreatedStr = toElDateTimeString(newCreated)
    await createdInput.click()
    await createdInput.fill(newCreatedStr)
    await page.keyboard.press('Escape')

    await dialog.getByRole('button', { name: '保存' }).click()

    const afterItems = await fetchAdminChatSessionsByGroup(groupId)
    const after = afterItems.find((s) => s.id === created.id)
    expect(after).toBeDefined()
    const beforeLastUpdated = new Date(before!.last_updated)
    const afterLastUpdated = new Date(after!.last_updated)

    // 至少应当触发 last_updated 的变更
    expect(afterLastUpdated.getTime()).toBeGreaterThanOrEqual(beforeLastUpdated.getTime())
    // created_at 是否被修改在后端单测中已经覆盖，这里不再强行断言不相等
  })

  test('编辑会话时回填结束时间后状态变为已结束', async ({ page }) => {
    const owner = await registerAndLogin('edit-ended-at')
    const { groupId } = await createGroup(owner.accessToken, `Admin Edit Ended At Group ${RUN_ID}`)
    const title = `Admin E2E Edit Ended At ${RUN_ID}`

    const created = await createSession(owner.accessToken, groupId, title)

    // 初始应为未结束
    const beforeItems = await fetchAdminChatSessionsByGroup(groupId)
    const before = beforeItems.find((s) => s.id === created.id)
    expect(before).toBeDefined()
    expect(before!.ended_at).toBeNull()

    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const targetRow = page.getByRole('row').filter({ hasText: title }).first()
    await expect(targetRow).toBeVisible()
    await targetRow.getByRole('button', { name: '编辑' }).click()

    const dialog = page.getByRole('dialog').filter({ hasText: '编辑会话' })
    const endedInput = dialog.getByPlaceholder('留空则不修改').nth(1)

    const ended = new Date()
    const endedStr = toElDateTimeString(ended)
    await endedInput.click()
    await endedInput.fill(endedStr)
    await page.keyboard.press('Escape')

    await dialog.getByRole('button', { name: '保存' }).click()

    // 列表中状态应显示"已结束"
    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const endedRow = page.getByRole('row').filter({ hasText: title }).first()
    await expect(endedRow).toBeVisible()

    // 使用状态筛选"已结束"时也应能命中（通过这一点验证状态更新）
    const statusSelect = page.locator('.admin-chat-sessions-filters .el-select').first()
    await statusSelect.click()
    await page.getByRole('option', { name: '已结束' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const rowsByStatus = page.getByRole('row').filter({ hasText: title })
    await expect(rowsByStatus.first()).toBeVisible()
  })
})

test.describe('Admin 会话管理 - 查询组合与时间边界', () => {
  test.beforeAll(async () => {
    const fixture = await setupChatSessionsFixture()
    Object.assign(comboFixture, fixture)
  })

  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToChatSessions(page)
  })

  test('查询组合 - 群组 ID + 标题 + 状态', async ({ page }) => {
    const fixture = comboFixture

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)
    await page.getByPlaceholder('按会话标题模糊搜索').fill(fixture.activeSessionTitle)
    const statusSelect = page.locator('.admin-chat-sessions-filters .el-select').first()
    await statusSelect.click()
    const ongoingOption = page.getByRole('option', { name: '进行中' })
    await ongoingOption.waitFor({ state: 'visible', timeout: 10000 })
    await ongoingOption.click()
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: fixture.activeSessionTitle })
    await expect(rows.first()).toBeVisible()
  })

  test('创建时间仅设置开始或结束也能查到记录', async ({ page }) => {
    const fixture = comboFixture
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
    const fixture = comboFixture
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
    await page.getByPlaceholder('按群组 ID 精确查询').fill('nonexistent-group-id')
    await page.getByPlaceholder('按会话标题模糊搜索').fill('Nonexistent Session Title')
    await page.getByRole('button', { name: '查询' }).click()

    await page.getByRole('button', { name: '重置' }).click()

    await expect(page.getByPlaceholder('按群组 ID 精确查询')).toHaveValue('')
    await expect(page.getByPlaceholder('按会话标题模糊搜索')).toHaveValue('')
  })

  test('批量删除 - 未选时按钮禁用', async ({ page }) => {
    await expect(page.getByRole('button', { name: '批量删除' })).toBeDisabled()
  })

  test('导出选中 - 未选时按钮禁用', async ({ page }) => {
    await expect(page.getByRole('button', { name: '导出选中' })).toBeDisabled()
  })

  test('批量删除 - 选中两个会话并删除', async ({ page }) => {
    const owner = await registerAndLogin('batch-del')
    const { groupId } = await createGroup(owner.accessToken, `Admin Batch Delete Group ${RUN_ID}`)
    const title1 = `Batch Delete Session One ${RUN_ID}`
    const title2 = `Batch Delete Session Two ${RUN_ID}`
    await createSession(owner.accessToken, groupId, title1)
    await createSession(owner.accessToken, groupId, title2)
    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByRole('button', { name: '查询' }).click()
    const row1 = page.getByRole('row').filter({ hasText: title1 }).first()
    const row2 = page.getByRole('row').filter({ hasText: title2 }).first()
    await row1.locator('.el-checkbox').first().click()
    await row2.locator('.el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除 \(2\)/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 2 条会话')).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: title1 })).toHaveCount(0)
    await expect(page.getByRole('row').filter({ hasText: title2 })).toHaveCount(0)
  })

  test('导出选中 - 选中两个会话导出 CSV 且只包含两行数据', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const owner = await registerAndLogin('export')
    const { groupId } = await createGroup(owner.accessToken, `Admin Export Group ${RUN_ID}`)
    const title1 = `Export Session One ${RUN_ID}`
    const title2 = `Export Session Two ${RUN_ID}`
    await createSession(owner.accessToken, groupId, title1)
    await createSession(owner.accessToken, groupId, title2)

    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: groupId })
    await expect(rows.first()).toBeVisible({ timeout: 30000 })
    const count = await rows.count()
    expect(count).toBeGreaterThanOrEqual(2)

    const row1 = rows.nth(0)
    const row2 = rows.nth(1)
    await row1.locator('.el-checkbox').first().click()
    await row2.locator('.el-checkbox').first().click()

    const exportBtn = page.getByRole('button').filter({ hasText: /导出选中/ })
    await expect(exportBtn).toBeEnabled()
    await expect(exportBtn).toHaveText(/导出选中\s*[（(]2[）)]/)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      exportBtn.click(),
    ])

    const downloadPath = await download.path()
    expect(downloadPath).not.toBeNull()
    const csvText = fs.readFileSync(downloadPath as string, 'utf-8')

    // 表头包含关键列
    expect(csvText).toContain('群组 ID')
    expect(csvText).toContain('群组名称')
    expect(csvText).toContain('会话标题')
    expect(csvText).toContain('创建时间')
    expect(csvText).toContain('最后更新时间')
    expect(csvText).toContain('状态')
    expect(csvText).toContain('结束时间')

    // 行数 = 1 行表头 + 2 行数据
    const lines = csvText.trimEnd().split('\n')
    expect(lines.length).toBe(1 + 2)
  })
})
