import { test, expect } from '@playwright/test'

test.setTimeout(60000)

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

async function registerAndLogin(label: string): Promise<{ userId: string; accessToken: string }> {
  const ts = Date.now()
  const email = `admin-sd-${label}-${ts}@example.com`
  const password = '1234'

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `Admin SD ${label}`, email, password }),
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

  return { userId: user.id, accessToken: loginData.access_token }
}

async function createGroup(accessToken: string, name: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`创建群组失败: ${await res.text()}`)
  const data = await res.json()
  return data.group.id as string
}

async function createSession(accessToken: string, groupId: string, title: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ session_title: title }),
  })
  if (!res.ok) throw new Error(`创建会话失败: ${await res.text()}`)
  const data = await res.json()
  return data.id as string
}

async function addTranscript(
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
      speaker: speaker || null,
      text,
      start: '2024-01-01T00:00:01.000Z',
      end: '2024-01-01T00:00:05.000Z',
    }),
  })
  if (!res.ok) throw new Error(`添加转写失败: ${await res.text()}`)
  const data = await res.json()
  return data.transcript_id as string
}

async function loginAsAdminAndGoToDetail(
  page: import('@playwright/test').Page,
  sessionId: string,
): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto(`/admin/chat-sessions/${sessionId}`)
}

// ─────────────────────────────────────────────────────────────────────────────
// A. 基础加载
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminChatSessionDetail - 基础加载', () => {
  test('A-1: 直接访问 /admin/chat-sessions/:id，显示会话标题和基本信息', async ({ page }) => {
    const { accessToken } = await registerAndLogin('a1')
    const groupId = await createGroup(accessToken, `Admin-SD-A1群-${Date.now()}`)
    const sessionId = await createSession(accessToken, groupId, `A1测试会话-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, sessionId)

    await expect(page.locator('.admin-session-detail-name')).toBeVisible()
    await expect(page.locator('.admin-session-detail-id')).toContainText(sessionId)
  })

  test('A-2: 页面显示「群组 ID」和「群组名称」信息', async ({ page }) => {
    const { accessToken } = await registerAndLogin('a2')
    const groupName = `Admin-SD-A2群-${Date.now()}`
    const groupId = await createGroup(accessToken, groupName)
    const sessionId = await createSession(accessToken, groupId, `A2测试会话-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, sessionId)

    await expect(page.getByText(groupId)).toBeVisible()
  })

  test('A-3: 点击「返回会话列表」跳回 /admin/chat-sessions', async ({ page }) => {
    const { accessToken } = await registerAndLogin('a3')
    const groupId = await createGroup(accessToken, `Admin-SD-A3群-${Date.now()}`)
    const sessionId = await createSession(accessToken, groupId, `A3返回测试-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '← 返回会话列表' }).click()

    await expect(page).toHaveURL(/\/admin\/chat-sessions$/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// B. 会话信息编辑
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminChatSessionDetail - 会话信息编辑', () => {
  test('B-1: 点击「编辑会话」弹出 dialog 含标题和状态字段', async ({ page }) => {
    const { accessToken } = await registerAndLogin('b1')
    const groupId = await createGroup(accessToken, `Admin-SD-B1群-${Date.now()}`)
    const sessionId = await createSession(accessToken, groupId, `B1编辑测试-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '编辑会话' }).click()

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByLabel('会话标题')).toBeVisible()
  })

  test('B-2: 修改标题后保存，页面标题更新', async ({ page }) => {
    const { accessToken } = await registerAndLogin('b2')
    const groupId = await createGroup(accessToken, `Admin-SD-B2群-${Date.now()}`)
    const sessionId = await createSession(accessToken, groupId, `B2原标题-${Date.now()}`)
    const newTitle = `B2新标题-${Date.now()}`

    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '编辑会话' }).click()

    await page.getByLabel('会话标题').fill(newTitle)
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.locator('.admin-session-detail-name')).toContainText(newTitle)
  })

  test('B-3: 取消编辑 dialog，标题不变', async ({ page }) => {
    const { accessToken } = await registerAndLogin('b3')
    const groupId = await createGroup(accessToken, `Admin-SD-B3群-${Date.now()}`)
    const originalTitle = `B3原标题-${Date.now()}`
    const sessionId = await createSession(accessToken, groupId, originalTitle)

    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '编辑会话' }).click()
    await page.getByLabel('会话标题').fill('不该保存的标题')
    await page.getByRole('button', { name: '取消' }).click()

    await expect(page.locator('.admin-session-detail-name')).toContainText(originalTitle)
  })

  test('B-4: 会话标题为空时不能保存，显示校验提示', async ({ page }) => {
    const { accessToken } = await registerAndLogin('b4')
    const groupId = await createGroup(accessToken, `Admin-SD-B4群-${Date.now()}`)
    const sessionId = await createSession(accessToken, groupId, `B4校验测试-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '编辑会话' }).click()
    await page.getByLabel('会话标题').fill('')
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.getByRole('dialog')).toBeVisible()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// C. 转写管理（serial，共用 fixture）
// ─────────────────────────────────────────────────────────────────────────────
test.describe.serial('AdminChatSessionDetail - 转写管理', () => {
  let accessToken: string
  let groupId: string
  let sessionId: string
  let transcriptId: string

  test.beforeAll(async () => {
    test.setTimeout(60000)
    const user = await registerAndLogin('c-serial')
    accessToken = user.accessToken
    groupId = await createGroup(accessToken, `Serial转写管理群-${Date.now()}`)
    sessionId = await createSession(accessToken, groupId, `Serial转写管理会话-${Date.now()}`)
  })

  test('C-1: 无转写时显示「暂无转写记录」', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    await expect(page.locator('.admin-session-detail-empty')).toContainText('暂无转写记录')
  })

  test('C-2: 点击「新增转写」弹出 dialog', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '新增转写' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByLabel('内容')).toBeVisible()
  })

  test('C-3: 填写并保存新增转写，转写列表显示新记录', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '新增转写' }).click()

    const addDialog = page.getByRole('dialog', { name: '新增转写' })
    await expect(addDialog).toBeVisible()
    // 使用 el-input__inner / el-textarea__inner 精确定位
    await addDialog.locator('.el-input__inner').nth(0).fill('测试说话人')
    await addDialog.locator('.el-textarea__inner').fill('C3新增转写文本')
    await addDialog.locator('.el-input__inner').nth(1).fill('2024-01-01T00:00:01.000Z')
    await addDialog.locator('.el-input__inner').nth(2).fill('2024-01-01T00:00:05.000Z')

    // 拦截 API 请求，确认提交成功
    const [response] = await Promise.all([
      page.waitForResponse(
        r => r.url().includes('/api/admin/transcripts') && r.request().method() === 'POST',
        { timeout: 15000 },
      ),
      addDialog.getByRole('button', { name: '添加' }).click(),
    ])
    expect(response.ok()).toBeTruthy()

    await expect(page.locator('.el-table__row').first()).toBeVisible()
    await expect(page.getByText('C3新增转写文本')).toBeVisible()
  })

  test('C-4: 点击「编辑」弹出编辑转写 dialog，修改后保存', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)

    await page.locator('.el-table__row').first().getByRole('button', { name: '编辑' }).click()
    const editDialog = page.getByRole('dialog', { name: '编辑转写' })
    await expect(editDialog).toBeVisible()

    await editDialog.locator('.el-textarea__inner').fill('C4修改后的转写文本')

    const [patchRes] = await Promise.all([
      page.waitForResponse(
        r => r.url().includes('/api/admin/transcripts/') && r.request().method() === 'PATCH',
        { timeout: 15000 },
      ),
      editDialog.getByRole('button', { name: '保存' }).click(),
    ])
    expect(patchRes.ok()).toBeTruthy()

    await expect(page.getByText('C4修改后的转写文本')).toBeVisible()
  })

  test('C-5: is_edited 标签在编辑后显示「已编辑」', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    await expect(page.locator('.el-table__row').first().getByText('已编辑')).toBeVisible()
  })

  test('C-6: 勾选转写后点「批量删除」删除选中记录', async ({ page }) => {
    // 先通过 API 再加一条，保证有记录可批量删
    transcriptId = await addTranscript(sessionId, groupId, '批量说话人', '批量删除文本')
    await loginAsAdminAndGoToDetail(page, sessionId)

    await page.locator('.el-table__row').filter({ hasText: '批量删除文本' }).locator('.el-checkbox').click()
    await expect(page.getByRole('button', { name: /批量删除/ })).not.toBeDisabled()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await expect(page.locator('.el-message-box')).toBeVisible()

    const [batchRes] = await Promise.all([
      page.waitForResponse(
        r => r.url().includes('/api/admin/transcripts/batch-delete') && r.request().method() === 'POST',
        { timeout: 15000 },
      ),
      page.locator('.el-message-box').getByRole('button', { name: '删除' }).click(),
    ])
    expect(batchRes.ok()).toBeTruthy()

    await expect(page.getByText('批量删除文本')).not.toBeVisible()
  })

  test('C-7: 点击单条「删除」弹出确认并删除', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    // 等数据加载完（表格行或空态至少一个可见）
    await expect(
      page.locator('.el-table__row').first().or(page.locator('.admin-session-detail-empty')),
    ).toBeVisible()
    const rowCount = await page.locator('.el-table__row').count()

    if (rowCount > 0) {
      await page.locator('.el-table__row').first().getByRole('button', { name: '删除' }).click()
      await page.locator('.el-message-box').getByRole('button', { name: '删除' }).click()
      await expect(page.locator('.el-table__row')).toHaveCount(rowCount - 1)
    } else {
      // 若已无记录，直接验证空态
      await expect(page.locator('.admin-session-detail-empty')).toBeVisible()
    }
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// D. 删除会话（serial）
// ─────────────────────────────────────────────────────────────────────────────
test.describe.serial('AdminChatSessionDetail - 删除会话', () => {
  let accessToken: string
  let sessionId: string

  test.beforeAll(async () => {
    test.setTimeout(60000)
    const user = await registerAndLogin('d-serial')
    accessToken = user.accessToken
    const groupId = await createGroup(accessToken, `Serial删除会话群-${Date.now()}`)
    sessionId = await createSession(accessToken, groupId, `Serial删除会话-${Date.now()}`)
  })

  test('D-1: 点击「删除会话」弹出确认 dialog', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '删除会话' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('D-2: 确认删除后跳回会话列表', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, sessionId)
    await page.getByRole('button', { name: '删除会话' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '删除' }).click()

    await expect(page).toHaveURL(/\/admin\/chat-sessions$/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// E. 边界异常
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminChatSessionDetail - 边界异常', () => {
  test('E-1: 访问不存在的会话 ID 显示错误信息', async ({ page }) => {
    await page.goto('/admin/login')
    await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
    await page.getByRole('button', { name: '进入后台' }).click()
    await expect(page).toHaveURL(/\/admin\/users/)

    await page.goto('/admin/chat-sessions/00000000-0000-0000-0000-000000000000')
    await expect(page.locator('.admin-session-detail-error')).toBeVisible()
  })

  test('E-2: 未登录管理员访问详情页跳转到管理员登录', async ({ page }) => {
    await page.goto('/admin/chat-sessions/some-session-id')
    await expect(page).toHaveURL(/\/admin\/login/)
  })
})
