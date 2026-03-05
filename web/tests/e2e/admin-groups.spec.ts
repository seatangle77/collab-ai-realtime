import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

/** 仅做前置：登录并进入群组管理页（不在此 spec 内测登录行为，登录已在用户管理 E2E 覆盖） */
async function loginAsAdminAndGoToGroups(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto('/admin/groups')
  await expect(page.getByRole('heading', { name: '群组管理' })).toBeVisible()
}

/** 通过 App 端接口注册用户并创建群组，供 Admin 列表/筛选/编辑/删除使用 */
async function createGroupViaAppApi(): Promise<{
  groupId: string
  groupName: string
  createdAt: Date
}> {
  const email = `e2e-group-${Date.now()}@example.com`
  const groupName = `E2E群组${Date.now()}`

  await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'E2E Group User', email, password: 'Pass123' }),
  })

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: 'Pass123' }),
  })
  const loginData = await loginRes.json()
  const token = loginData.access_token

  const groupRes = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name: groupName }),
  })
  const groupData = await groupRes.json()
  const group = groupData.group
  return {
    groupId: group.id,
    groupName: group.name,
    createdAt: new Date(group.created_at),
  }
}

const shared: {
  groupId: string
  groupName: string
  createdAt: Date
} = {} as any

test.describe.serial('Admin 群组管理页面', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToGroups(page)
  })

  test('1. 通过 App 接口创建群组并在列表中看到', async ({ page }) => {
    const created = await createGroupViaAppApi()
    shared.groupId = created.groupId
    shared.groupName = created.groupName
    shared.createdAt = created.createdAt

    await page.getByPlaceholder('按群组名称模糊搜索').fill(shared.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.groupName }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText(shared.groupId)
  })

  test('2. 按名称模糊筛选', async ({ page }) => {
    const partName = shared.groupName.slice(0, 6)
    await page.getByPlaceholder('按群组名称模糊搜索').fill(partName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.groupName }).first()
    await expect(row).toBeVisible()
  })

  test('3. 按状态筛选（启用）', async ({ page }) => {
    await page.getByPlaceholder('按群组名称模糊搜索').fill(shared.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    await page.locator('.admin-groups-filters .el-select').first().click()
    await page.getByRole('option', { name: '启用' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.groupName }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('启用')
  })

  test('4. 按创建时间范围筛选', async ({ page }) => {
    const start = new Date(shared.createdAt.getTime() - 60 * 60 * 1000)
    const end = new Date(shared.createdAt.getTime() + 60 * 60 * 1000)
    const startStr = start.toISOString().slice(0, 19).replace('T', ' ')
    const endStr = end.toISOString().slice(0, 19).replace('T', ' ')

    const startInput = page.locator('.admin-groups-filters').getByPlaceholder('开始时间')
    const endInput = page.locator('.admin-groups-filters').getByPlaceholder('结束时间')
    await startInput.click()
    await startInput.fill(startStr)
    await endInput.fill(endStr)

    await page.getByRole('button', { name: '查询' }).click()
    const row = page.getByRole('row').filter({ hasText: shared.groupName }).first()
    await expect(row).toBeVisible()
  })

  test('5. 编辑群组', async ({ page }) => {
    await page.getByPlaceholder('按群组名称模糊搜索').fill(shared.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.groupName }).first()
    await row.getByRole('button', { name: '编辑' }).click()

    const editDialog = page.getByRole('dialog', { name: '编辑群组' })
    await expect(editDialog).toBeVisible()

    const nameInput = editDialog.getByLabel('名称')
    await nameInput.fill('')
    await nameInput.fill(`${shared.groupName}-已编辑`)
    await editDialog.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('更新群组成功')).toBeVisible()
    shared.groupName = `${shared.groupName}-已编辑`
  })

  test('6. 删除群组', async ({ page }) => {
    await page.getByPlaceholder('按群组名称模糊搜索').fill(shared.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.groupName }).first()
    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()

    await expect(page.getByText('删除群组成功')).toBeVisible()
  })

  test('7. 删除后查不到该群组', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按群组名称模糊搜索').fill(shared.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    await expect(page.getByRole('row').filter({ hasText: shared.groupName })).toHaveCount(0)
  })
})

// ---------------------------------------------------------------------------
// 查询条件与组合、创建时间专项、边界（不测登录）
// ---------------------------------------------------------------------------
test.describe('Admin 群组管理 - 查询与边界', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToGroups(page)
  })

  test('查询条件组合 - 名称 + 状态', async ({ page }) => {
    const created = await createGroupViaAppApi()
    await page.getByPlaceholder('按群组名称模糊搜索').fill(created.groupName)
    await page.locator('.admin-groups-filters .el-select').first().click()
    await page.getByRole('option', { name: '启用' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: created.groupName }).first()
    await expect(row).toBeVisible()
  })

  test('创建时间专项 - 范围外查不到', async ({ page }) => {
    const created = await createGroupViaAppApi()
    const wayPast = new Date(created.createdAt.getTime() - 24 * 60 * 60 * 1000)
    const wayPastEnd = new Date(wayPast.getTime() + 60 * 60 * 1000)

    const startInput = page.locator('.admin-groups-filters').getByPlaceholder('开始时间')
    const endInput = page.locator('.admin-groups-filters').getByPlaceholder('结束时间')
    await startInput.click()
    await startInput.fill(wayPast.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(wayPastEnd.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByRole('button', { name: '查询' }).click()

    await expect(page.getByRole('row').filter({ hasText: created.groupName })).toHaveCount(0)
  })

  test('编辑 - 名称为空时表单校验阻止保存', async ({ page }) => {
    const created = await createGroupViaAppApi()
    await page.getByPlaceholder('按群组名称模糊搜索').fill(created.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: created.groupName }).first()
    await row.getByRole('button', { name: '编辑' }).click()

    const editDialog = page.getByRole('dialog', { name: '编辑群组' })
    await editDialog.getByLabel('名称').fill('')
    await editDialog.getByRole('button', { name: '保存' }).click()

    await expect(editDialog.getByText('请输入群组名称')).toBeVisible()
    await expect(editDialog).toBeVisible()
  })

  test('删除 - 取消删除时群组仍在列表中', async ({ page }) => {
    const created = await createGroupViaAppApi()
    await page.getByPlaceholder('按群组名称模糊搜索').fill(created.groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: created.groupName }).first()
    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '取消' }).click()

    await expect(page.getByRole('row').filter({ hasText: created.groupName })).toBeVisible()
  })

  test('重置筛选 - 条件清空且列表恢复', async ({ page }) => {
    await page.getByPlaceholder('按群组名称模糊搜索').fill('不存在的群组名')
    await page.getByRole('button', { name: '查询' }).click()
    await page.getByRole('button', { name: '重置' }).click()

    await expect(page.getByPlaceholder('按群组名称模糊搜索')).toHaveValue('')
  })
})
