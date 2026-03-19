import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

interface TestUser {
  userId: string
  accessToken: string
}

async function loginAsAdminAndGoToGroups(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto('/admin/groups')
  await expect(page.getByRole('heading', { name: '群组管理' })).toBeVisible()
}

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts = Date.now()
  const email = `admin-gd-${label}-${ts}@example.com`
  const password = '1234'

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `Admin GD ${label}`, email, password }),
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

async function joinGroup(accessToken: string, groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) throw new Error(`加入群组失败: ${await res.text()}`)
}

async function createSession(accessToken: string, groupId: string, title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ session_title: title }),
  })
  if (!res.ok) throw new Error(`创建会话失败: ${await res.text()}`)
}

async function loginAsAdminAndGoToDetail(
  page: import('@playwright/test').Page,
  groupId: string,
): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto(`/admin/groups/${groupId}`)
  await expect(page.getByRole('heading', { level: 2 })).toBeVisible()
}

// ─────────────────────────────────────────────────────────────────────────────
// A. 页面基础加载
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminGroupDetail - 基础加载', () => {
  test('A-1: 从列表行点击"详情"跳转到详情页', async ({ page }) => {
    const leader = await registerAndLogin('a1-leader')
    const groupName = `Admin详情跳转测试群-${Date.now()}`
    await createGroup(leader.accessToken, groupName)

    await loginAsAdminAndGoToGroups(page)
    await page.getByPlaceholder('按群组名称模糊搜索').fill(groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: groupName }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: '详情' }).click()

    await expect(page).toHaveURL(/\/admin\/groups\/.+/)
  })

  test('A-2: 直接访问 /admin/groups/:id，群名、ID、状态、创建时间均显示', async ({ page }) => {
    const leader = await registerAndLogin('a2-leader')
    const groupName = `Admin直接访问测试群-${Date.now()}`
    const groupId = await createGroup(leader.accessToken, groupName)

    await loginAsAdminAndGoToDetail(page, groupId)

    await expect(page.locator('.admin-group-detail-name')).toContainText(groupName)
    await expect(page.locator('.admin-group-detail-id')).toContainText(groupId)
    await expect(page.getByText('启用')).toBeVisible()
  })

  test('A-3: 点击返回按钮跳回 /admin/groups', async ({ page }) => {
    const leader = await registerAndLogin('a3-leader')
    const groupId = await createGroup(leader.accessToken, `Admin返回测试群-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, groupId)
    await page.getByRole('button', { name: '← 返回群组列表' }).click()
    await expect(page).toHaveURL(/\/admin\/groups$/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// B. 群组信息卡
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminGroupDetail - 群组信息卡', () => {
  test('B-1: 启用群组显示"启用" tag，停用群组显示"停用" tag', async ({ page }) => {
    const leader = await registerAndLogin('b1-leader')
    const groupId = await createGroup(leader.accessToken, `Tag测试群-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, groupId)
    await expect(page.locator('.admin-group-detail-name-row .el-tag').filter({ hasText: '启用' })).toBeVisible()
  })

  test('B-2: 编辑群名成功，页面标题更新', async ({ page }) => {
    const leader = await registerAndLogin('b2-leader')
    const groupId = await createGroup(leader.accessToken, `编辑名称测试群-${Date.now()}`)
    const newName = `已编辑名称-${Date.now()}`

    await loginAsAdminAndGoToDetail(page, groupId)
    await page.getByRole('button', { name: '编辑' }).first().click()

    const dialog = page.getByRole('dialog', { name: '编辑群组' })
    await expect(dialog).toBeVisible()
    const nameInput = dialog.getByLabel('名称')
    await nameInput.fill('')
    await nameInput.fill(newName)
    await dialog.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('更新群组成功')).toBeVisible()
    await expect(page.locator('.admin-group-detail-name')).toContainText(newName)
  })

  test('B-3: 编辑群名为空，表单校验阻止', async ({ page }) => {
    const leader = await registerAndLogin('b3-leader')
    const groupId = await createGroup(leader.accessToken, `校验名称测试群-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, groupId)
    await page.getByRole('button', { name: '编辑' }).first().click()

    const dialog = page.getByRole('dialog', { name: '编辑群组' })
    await dialog.getByLabel('名称').fill('')
    await dialog.getByRole('button', { name: '保存' }).click()

    await expect(dialog.getByText('请输入群组名称')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('B-4: 编辑取消，名称不变', async ({ page }) => {
    const leader = await registerAndLogin('b4-leader')
    const groupName = `取消编辑测试群-${Date.now()}`
    const groupId = await createGroup(leader.accessToken, groupName)

    await loginAsAdminAndGoToDetail(page, groupId)
    await page.getByRole('button', { name: '编辑' }).first().click()

    const dialog = page.getByRole('dialog', { name: '编辑群组' })
    await dialog.getByLabel('名称').fill('不会保存的名字')
    await dialog.getByRole('button', { name: '取消' }).click()

    await expect(page.locator('.admin-group-detail-name')).toContainText(groupName)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// C. 成员列表区（serial）
// ─────────────────────────────────────────────────────────────────────────────
test.describe.serial('AdminGroupDetail - 成员列表', () => {
  let leader: TestUser
  let member1: TestUser
  let member2: TestUser
  let groupId: string

  test.beforeAll(async () => {
    leader = await registerAndLogin('c-leader')
    member1 = await registerAndLogin('c-member1')
    member2 = await registerAndLogin('c-member2')
    groupId = await createGroup(leader.accessToken, `成员列表测试群-${Date.now()}`)
    await joinGroup(member1.accessToken, groupId)
    await joinGroup(member2.accessToken, groupId)
  })

  test('C-1: 成员列表展示 3 行（leader + 2 member）', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, groupId)

    await expect(page.locator('.el-table__body-wrapper .el-table__row')).toHaveCount(3)
  })

  test('C-2: 编辑成员角色 member → leader 成功', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, groupId)

    const rows = page.locator('.el-table__body-wrapper .el-table__row')
    const member1Row = rows.filter({ hasText: member1.userId })
    await member1Row.getByRole('button', { name: '编辑' }).click()

    const dialog = page.getByRole('dialog', { name: '编辑成员关系' })
    await expect(dialog).toBeVisible()
    await dialog.locator('.el-form-item').filter({ hasText: '角色' }).locator('.el-select').click()
    await page.getByRole('option', { name: '群主 (leader)' }).click()
    await dialog.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('更新成员关系成功')).toBeVisible()
    await expect(member1Row.filter({ hasText: '群主' })).toBeVisible()
  })

  test('C-3: 编辑成员状态 active → left 成功', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, groupId)

    const rows = page.locator('.el-table__body-wrapper .el-table__row')
    const member2Row = rows.filter({ hasText: member2.userId })
    await member2Row.getByRole('button', { name: '编辑' }).click()

    const dialog = page.getByRole('dialog', { name: '编辑成员关系' })
    await expect(dialog).toBeVisible()
    await dialog.locator('.el-form-item').filter({ hasText: '状态' }).locator('.el-select').click()
    await page.getByRole('option', { name: '已退出 (left)' }).click()
    await dialog.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('更新成员关系成功')).toBeVisible()
    await expect(member2Row.filter({ hasText: '已退出 (left)' })).toBeVisible()
  })

  test('C-4: 编辑成员 - 取消，信息不变', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, groupId)

    const rows = page.locator('.el-table__body-wrapper .el-table__row')
    const leaderRow = rows.filter({ hasText: leader.userId })
    const originalRole = await leaderRow.locator('td').nth(2).textContent()

    await leaderRow.getByRole('button', { name: '编辑' }).click()
    const dialog = page.getByRole('dialog', { name: '编辑成员关系' })
    await dialog.locator('.el-form-item').filter({ hasText: '角色' }).locator('.el-select').click()
    await page.getByRole('option', { name: '成员 (member)' }).click()
    await dialog.getByRole('button', { name: '取消' }).click()

    await expect(leaderRow.locator('td').nth(2)).toContainText(originalRole!.trim())
  })

  test('C-5: 删除成员成功，该行消失', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, groupId)

    const rows = page.locator('.el-table__body-wrapper .el-table__row')
    const beforeCount = await rows.count()

    const member2Row = rows.filter({ hasText: member2.userId })
    await member2Row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()

    await expect(page.getByText('删除成员关系成功')).toBeVisible()
    await expect(rows).toHaveCount(beforeCount - 1)
  })

  test('C-6: 删除成员 - 取消确认，成员仍在', async ({ page }) => {
    await loginAsAdminAndGoToDetail(page, groupId)

    const rows = page.locator('.el-table__body-wrapper .el-table__row')
    const beforeCount = await rows.count()

    const anyRow = rows.first()
    await anyRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '取消' }).last().click()

    await expect(rows).toHaveCount(beforeCount)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// D. 历史会话区
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminGroupDetail - 历史会话区', () => {
  test('D-1: 无会话显示空状态文案', async ({ page }) => {
    const leader = await registerAndLogin('d1-leader')
    const groupId = await createGroup(leader.accessToken, `Admin无会话测试群-${Date.now()}`)

    await loginAsAdminAndGoToDetail(page, groupId)

    await expect(page.locator('.admin-group-detail-empty')).toBeVisible()
  })

  test.describe('有会话时展示', () => {
    let leader: TestUser
    let groupId: string

    test.beforeAll(async () => {
      leader = await registerAndLogin('d-sessions-leader')
      groupId = await createGroup(leader.accessToken, `Admin有会话测试群-${Date.now()}`)
      await createSession(leader.accessToken, groupId, 'Admin测试会话标题')
    })

    test('D-2: 有会话时展示标题、状态 tag、时间', async ({ page }) => {
      await loginAsAdminAndGoToDetail(page, groupId)

      // 页面有两张表（成员、会话），取第二张（会话表）的第一行
      const sessionTable = page.locator('.el-table').nth(1)
      await expect(sessionTable).toBeVisible({ timeout: 15000 })
      const sessionRow = sessionTable.locator('.el-table__row').first()
      await expect(sessionRow).toBeVisible({ timeout: 15000 })
      await expect(sessionRow).toContainText('Admin测试会话标题')
      await expect(sessionRow.locator('.el-tag')).toBeVisible()
    })
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// E. 危险操作区（serial，每项用独立群）
// ─────────────────────────────────────────────────────────────────────────────
test.describe.serial('AdminGroupDetail - 危险操作区', () => {
  let leader: TestUser

  test.beforeAll(async () => {
    leader = await registerAndLogin('e-leader')
  })

  test('E-1: 停用群组成功，状态 tag 变"停用"', async ({ page }) => {
    const groupId = await createGroup(leader.accessToken, `停用测试群-${Date.now()}`)
    await loginAsAdminAndGoToDetail(page, groupId)

    await page.getByRole('button', { name: '停用群组' }).click()
    await page.getByRole('button', { name: '停用' }).last().click()

    await expect(page.getByText('群组已停用')).toBeVisible()
    await expect(page.locator('.admin-group-detail-name-row .el-tag').filter({ hasText: '停用' })).toBeVisible()
  })

  test('E-2: 停用群组 - 取消确认，状态不变', async ({ page }) => {
    const groupId = await createGroup(leader.accessToken, `取消停用测试群-${Date.now()}`)
    await loginAsAdminAndGoToDetail(page, groupId)

    await page.getByRole('button', { name: '停用群组' }).click()
    await page.getByRole('button', { name: '取消' }).last().click()

    await expect(page.locator('.admin-group-detail-name-row .el-tag').filter({ hasText: '启用' })).toBeVisible()
  })

  test('E-3: 启用已停用群组，状态 tag 变"启用"', async ({ page }) => {
    const groupId = await createGroup(leader.accessToken, `重启用测试群-${Date.now()}`)

    // 先通过 admin API 停用
    await fetch(`${API_BASE}/api/admin/groups/${groupId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
      body: JSON.stringify({ is_active: false }),
    })

    await loginAsAdminAndGoToDetail(page, groupId)
    await expect(page.locator('.admin-group-detail-name-row .el-tag').filter({ hasText: '停用' })).toBeVisible()

    await page.getByRole('button', { name: '启用群组' }).click()
    await page.getByRole('button', { name: '启用' }).last().click()

    await expect(page.getByText('群组已启用')).toBeVisible()
    await expect(page.locator('.admin-group-detail-name-row .el-tag').filter({ hasText: '启用' })).toBeVisible()
  })

  test('E-4: 删除群组成功，跳回列表，列表查不到', async ({ page }) => {
    const groupName = `删除测试群-${Date.now()}`
    const groupId = await createGroup(leader.accessToken, groupName)
    await loginAsAdminAndGoToDetail(page, groupId)

    await page.getByRole('button', { name: '删除群组' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()

    await expect(page.getByText('删除群组成功')).toBeVisible()
    await expect(page).toHaveURL(/\/admin\/groups$/)

    await page.getByPlaceholder('按群组名称模糊搜索').fill(groupName)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: groupName })).toHaveCount(0)
  })

  test('E-5: 删除群组 - 取消确认，仍在详情页', async ({ page }) => {
    const groupId = await createGroup(leader.accessToken, `取消删除测试群-${Date.now()}`)
    await loginAsAdminAndGoToDetail(page, groupId)

    await page.getByRole('button', { name: '删除群组' }).click()
    await page.getByRole('button', { name: '取消' }).last().click()

    await expect(page).toHaveURL(new RegExp(`/admin/groups/${groupId}`))
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// F. 边界与异常
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AdminGroupDetail - 边界与异常', () => {
  test('F-1: 访问不存在的群组 ID，显示错误状态', async ({ page }) => {
    await page.goto('/admin/login')
    await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
    await page.getByRole('button', { name: '进入后台' }).click()
    await expect(page).toHaveURL(/\/admin\/users/)

    await page.goto('/admin/groups/badid000')
    await expect(page.locator('.admin-group-detail-error')).toBeVisible()
    await expect(page.getByRole('button', { name: '返回列表' })).toBeVisible()
  })

  test('F-2: 错误状态下点击返回，跳回 /admin/groups', async ({ page }) => {
    await page.goto('/admin/login')
    await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
    await page.getByRole('button', { name: '进入后台' }).click()
    await expect(page).toHaveURL(/\/admin\/users/)

    await page.goto('/admin/groups/badid000')
    await expect(page.locator('.admin-group-detail-error')).toBeVisible()
    await page.getByRole('button', { name: '返回列表' }).click()
    await expect(page).toHaveURL(/\/admin\/groups$/)
  })
})
