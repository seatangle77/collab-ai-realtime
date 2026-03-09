import { test, expect } from '@playwright/test'
import fs from 'fs'

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

  test('0. 通过 Admin 页面新建启用群组并在列表中看到', async ({ page }) => {
    const groupName = `AdminUI群组-${Date.now()}`

    await page.getByRole('button', { name: '新建群组' }).click()

    const createDialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(createDialog).toBeVisible()

    const nameInput = createDialog.getByLabel('名称')
    await nameInput.fill(groupName)

    await createDialog.getByRole('button', { name: '创建' }).click()

    await expect(page.getByText('创建群组成功')).toBeVisible()

    await page.getByPlaceholder('按群组名称模糊搜索').fill(groupName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: groupName }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('启用')
  })

  test('0.1 通过 Admin 页面新建停用群组并通过状态筛选验证', async ({ page }) => {
    const groupName = `AdminUI群组-初始停用-${Date.now()}`

    await page.getByRole('button', { name: '新建群组' }).click()

    const createDialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(createDialog).toBeVisible()

    const nameInput = createDialog.getByLabel('名称')
    await nameInput.fill(groupName)

    // 默认是启用，切换为停用：Element Plus 的可点击区域在 .el-switch/.el-switch__core 上，input 本身是隐藏的
    const switchEl = createDialog.locator('.el-switch')
    await switchEl.waitFor()
    await switchEl.click()

    await createDialog.getByRole('button', { name: '创建' }).click()

    await expect(page.getByText('创建群组成功')).toBeVisible()

    await page.getByPlaceholder('按群组名称模糊搜索').fill(groupName)

    // 状态筛选为 启用 时查不到
    await page.locator('.admin-groups-filters .el-select').first().click()
    await page.getByRole('option', { name: '启用' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: groupName })).toHaveCount(0)

    // 状态筛选为 停用 时可以查到
    await page.locator('.admin-groups-filters .el-select').first().click()
    await page.getByRole('option', { name: '停用' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: groupName }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('停用')
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
    // 为避免本地时区与服务端存储时区差异导致边界误差，这里使用相对宽松的 ±24 小时区间
    const start = new Date(shared.createdAt.getTime() - 24 * 60 * 60 * 1000)
    const end = new Date(shared.createdAt.getTime() + 24 * 60 * 60 * 1000)
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

  test('新建群组 - 名称为空时表单校验阻止创建', async ({ page }) => {
    await page.getByRole('button', { name: '新建群组' }).click()

    const createDialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(createDialog).toBeVisible()

    const nameInput = createDialog.getByLabel('名称')
    await nameInput.fill('')

    await createDialog.getByRole('button', { name: '创建' }).click()

    await expect(createDialog.getByText('请输入群组名称')).toBeVisible()
    await expect(createDialog).toBeVisible()
  })

  test('新建群组 - 取消创建时不应产生新数据', async ({ page }) => {
    const groupName = `AdminUI群组-取消-${Date.now()}`

    await page.getByRole('button', { name: '新建群组' }).click()

    const createDialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(createDialog).toBeVisible()

    const nameInput = createDialog.getByLabel('名称')
    await nameInput.fill(groupName)

    await createDialog.getByRole('button', { name: '取消' }).click()

    await page.getByPlaceholder('按群组名称模糊搜索').fill(groupName)
    await page.getByRole('button', { name: '查询' }).click()

    await expect(page.getByRole('row').filter({ hasText: groupName })).toHaveCount(0)
  })

  test('新建群组 - 多次打开关闭弹窗时表单状态重置', async ({ page }) => {
    const tempName = `TempName-${Date.now()}`

    await page.getByRole('button', { name: '新建群组' }).click()
    let createDialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(createDialog).toBeVisible()

    let nameInput = createDialog.getByLabel('名称')
    await nameInput.fill(tempName)

    await createDialog.getByRole('button', { name: '取消' }).click()

    await page.getByRole('button', { name: '新建群组' }).click()
    createDialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(createDialog).toBeVisible()

    nameInput = createDialog.getByLabel('名称')
    await expect(nameInput).toHaveValue('')
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

  test('批量删除 - 未选时按钮禁用', async ({ page }) => {
    await expect(page.getByRole('button', { name: '批量删除' })).toBeDisabled()
  })

  test('导出选中 - 未选时按钮禁用', async ({ page }) => {
    await expect(page.getByRole('button', { name: '导出选中' })).toBeDisabled()
  })

  test('批量删除 - 选中两个群组并删除', async ({ page }) => {
    const g1 = await createGroupViaAppApi()
    const g2 = await createGroupViaAppApi()
    await page.getByPlaceholder('按群组名称模糊搜索').fill('E2E群组')
    await page.getByRole('button', { name: '查询' }).click()
    const row1 = page.getByRole('row').filter({ hasText: g1.groupName }).first()
    const row2 = page.getByRole('row').filter({ hasText: g2.groupName }).first()
    await expect(row1).toBeVisible({ timeout: 30000 })
    await expect(row2).toBeVisible({ timeout: 30000 })

    // Element Plus 的多选列在独立的固定列表格中，复选框不在该 row DOM 内，这里按顺序点击前两个复选框
    const checkboxes = page.locator('.el-table__body-wrapper .el-checkbox')
    await expect(checkboxes.nth(0)).toBeVisible({ timeout: 10000 })
    await expect(checkboxes.nth(1)).toBeVisible({ timeout: 10000 })
    await checkboxes.nth(0).click()
    await checkboxes.nth(1).click()
    await page.getByRole('button', { name: /批量删除 \(2\)/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 2 条群组')).toBeVisible()
  })

  test('导出选中 - 选中两个群组导出 CSV 且只包含选中行', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    await createGroupViaAppApi()
    await createGroupViaAppApi()
    await createGroupViaAppApi()

    // 通过公共前缀筛出这几个群组
    await page.getByPlaceholder('按群组名称模糊搜索').fill('E2E群组')
    await page.getByRole('button', { name: '查询' }).click()

    // 等待表格 loading 遮罩消失，避免点击被 .el-loading-mask 拦截
    const tableLoading = page.locator('.admin-groups-table .el-loading-mask')
    await tableLoading.first().waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {})

    // 只勾选前两个群组（复选框在固定列表格中，按顺序选择）
    const checkboxes = page.locator('.el-table__body-wrapper .el-checkbox')
    await expect(checkboxes.nth(0)).toBeVisible({ timeout: 10000 })
    await expect(checkboxes.nth(1)).toBeVisible({ timeout: 10000 })
    await checkboxes.nth(0).click()
    await checkboxes.nth(1).click()

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
    expect(csvText).toContain('名称')
    expect(csvText).toContain('创建时间')
    expect(csvText).toContain('状态')

    // 数据行数 = 表头 1 行 + 选中 2 行
    const lines = csvText.trimEnd().split('\n')
    expect(lines.length).toBe(1 + 2)
  })

  test('重置筛选 - 条件清空且列表恢复', async ({ page }) => {
    await page.getByPlaceholder('按群组名称模糊搜索').fill('不存在的群组名')
    await page.getByRole('button', { name: '查询' }).click()
    await page.getByRole('button', { name: '重置' }).click()

    await expect(page.getByPlaceholder('按群组名称模糊搜索')).toHaveValue('')
  })
})
