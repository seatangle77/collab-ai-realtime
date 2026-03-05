import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await expect(page.getByRole('heading', { name: '用户管理' })).toBeVisible()
}

/** 同一流程内共享的测试数据，按顺序执行时复用 */
const shared: {
  email: string
  initialName: string
  initialDeviceToken: string
  updatedName: string
  updatedDeviceToken: string
  createdAtClient: Date
  userId: string
} = {} as any

test.describe.serial('Admin 用户管理页面', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('1. 创建用户', async ({ page }) => {
    const now = Date.now()
    shared.email = `e2e-admin-user-${now}@example.com`
    shared.initialName = `E2E User ${now}`
    shared.initialDeviceToken = `e2e-device-${now}`
    shared.updatedName = `${shared.initialName}-updated`
    shared.updatedDeviceToken = `${shared.initialDeviceToken}-2`

    await page.getByRole('button', { name: '新建用户' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建用户' })
    await expect(createDialog).toBeVisible()

    await createDialog.getByLabel('姓名').fill(shared.initialName)
    await createDialog.getByLabel('邮箱').fill(shared.email)
    await createDialog.getByLabel('密码').fill('E2eTestPass123')
    await createDialog.getByLabel('设备 Token').fill(shared.initialDeviceToken)
    await createDialog.getByRole('button', { name: '创建' }).click()

    await expect(page.getByText('创建用户成功')).toBeVisible()
    shared.createdAtClient = new Date()
  })

  test('2. 按邮箱查询并确认创建成功', async ({ page }) => {
    await page.getByPlaceholder('按邮箱模糊搜索').fill(shared.email)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText(shared.initialName)
    await expect(row).toContainText(shared.initialDeviceToken)
  })

  test('3. 编辑用户', async ({ page }) => {
    await page.getByPlaceholder('按邮箱模糊搜索').fill(shared.email)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await row.getByRole('button', { name: '编辑' }).click()

    const editDialog = page.getByRole('dialog', { name: '编辑用户' })
    await expect(editDialog).toBeVisible()

    const nameInput = editDialog.getByLabel('姓名')
    await nameInput.fill('')
    await nameInput.fill(shared.updatedName)
    const deviceInput = editDialog.getByLabel('设备 Token')
    await deviceInput.fill('')
    await deviceInput.fill(shared.updatedDeviceToken)

    await editDialog.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('更新用户成功')).toBeVisible()
  })

  test('4. 再次按邮箱查询并读取用户 ID', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按邮箱模糊搜索').fill(shared.email)
    await page.getByRole('button', { name: '查询' }).click()

    const updatedRow = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(updatedRow).toBeVisible()
    await expect(updatedRow).toContainText(shared.updatedName)
    await expect(updatedRow).toContainText(shared.updatedDeviceToken)

    const idCell = updatedRow.getByRole('cell').first()
    shared.userId = (await idCell.innerText()).trim()
  })

  test('5. 按 ID 精确查询', async ({ page }) => {
    const idInput = page.locator('.admin-users-filters').getByPlaceholder('按用户 ID 精确查询')
    await idInput.fill(shared.userId)
    await page.getByRole('button', { name: '查询' }).click()

    const idRow = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(idRow).toBeVisible()
  })

  test('6. 按创建时间范围查询', async ({ page }) => {
    const start = new Date(shared.createdAtClient.getTime() - 10 * 60 * 1000)
    const end = new Date(shared.createdAtClient.getTime() + 10 * 60 * 1000)

    const datePicker = page.locator('.admin-users-filters').getByPlaceholder('开始时间')
    await datePicker.click()

    const startInput = page.locator('.admin-users-filters input').nth(4)
    const endInput = page.locator('.admin-users-filters input').nth(5)
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))

    await page.getByRole('button', { name: '查询' }).click()
    const timeRow = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(timeRow).toBeVisible()
  })

  test('7. 删除用户', async ({ page }) => {
    await page.getByPlaceholder('按邮箱模糊搜索').fill(shared.email)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除用户成功')).toBeVisible()
  })

  test('8. 验证删除后查不到该用户', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按邮箱模糊搜索').fill(shared.email)
    await page.getByRole('button', { name: '查询' }).click()

    await expect(page.getByRole('row').filter({ hasText: shared.email })).toHaveCount(0)
  })
})

// ---------------------------------------------------------------------------
// 边界与异常场景（独立用例，不依赖主流程数据）
// ---------------------------------------------------------------------------
test.describe('Admin 用户管理 - 边界与异常', () => {
  test('登录 - 错误密钥时最终停留在登录页', async ({ page }) => {
    await page.goto('/admin/login')
    await page.getByLabel('后台密钥').fill('wrong-key-12345')
    await page.getByRole('button', { name: '进入后台' }).click()
    // 会先跳到 /admin/users，请求接口 401 后再被重定向回 /admin/login
    await expect(page).toHaveURL(/\/admin\/login/, { timeout: 15_000 })
  })

  test('创建用户 - 姓名为空时表单校验阻止提交', async ({ page }) => {
    await loginAsAdmin(page)
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })

    await dialog.getByLabel('邮箱').fill('e2e-validation@example.com')
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()

    await expect(dialog.getByText('请输入姓名')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('创建用户 - 邮箱格式错误时表单校验', async ({ page }) => {
    await loginAsAdmin(page)
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })

    await dialog.getByLabel('姓名').fill('Test')
    await dialog.getByLabel('邮箱').fill('not-an-email')
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()

    await expect(dialog.getByText('邮箱格式不正确')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('创建用户 - 密码为空时表单校验', async ({ page }) => {
    await loginAsAdmin(page)
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })

    await dialog.getByLabel('姓名').fill('Test')
    await dialog.getByLabel('邮箱').fill('e2e-nopass@example.com')
    await dialog.getByRole('button', { name: '创建' }).click()

    await expect(dialog.getByText('请输入初始密码')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('创建用户 - 重复邮箱时后端报错并前端提示', async ({ page }) => {
    await loginAsAdmin(page)
    const dupEmail = `e2e-dup-${Date.now()}@example.com`

    await page.getByRole('button', { name: '新建用户' }).click()
    let dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('First')
    await dialog.getByLabel('邮箱').fill(dupEmail)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByRole('button', { name: '新建用户' }).click()
    dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('Second')
    await dialog.getByLabel('邮箱').fill(dupEmail)
    await dialog.getByLabel('密码').fill('Pass456')
    await dialog.getByRole('button', { name: '创建' }).click()

    await expect(page.getByText('邮箱已被注册')).toBeVisible({ timeout: 8000 })
  })

  test('编辑用户 - 姓名为空时表单校验阻止保存', async ({ page }) => {
    await loginAsAdmin(page)
    const email = `e2e-edit-validation-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建用户' })
    await createDialog.getByLabel('姓名').fill('Original')
    await createDialog.getByLabel('邮箱').fill(email)
    await createDialog.getByLabel('密码').fill('Pass123')
    await createDialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    const row = page.getByRole('row').filter({ hasText: email }).first()
    await row.getByRole('button', { name: '编辑' }).click()

    const editDialog = page.getByRole('dialog', { name: '编辑用户' })
    await editDialog.getByLabel('姓名').fill('')
    await editDialog.getByRole('button', { name: '保存' }).click()

    await expect(editDialog.getByText('请输入姓名')).toBeVisible()
    await expect(editDialog).toBeVisible()
  })

  test('删除 - 取消删除时用户仍在列表中', async ({ page }) => {
    await loginAsAdmin(page)
    const email = `e2e-cancel-delete-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建用户' })
    await createDialog.getByLabel('姓名').fill('Keep')
    await createDialog.getByLabel('邮箱').fill(email)
    await createDialog.getByLabel('密码').fill('Pass123')
    await createDialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    const row = page.getByRole('row').filter({ hasText: email }).first()
    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '取消' }).click()

    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })

  test('重置筛选 - 条件清空且列表恢复', async ({ page }) => {
    await loginAsAdmin(page)
    await page.getByPlaceholder('按邮箱模糊搜索').fill('some-nonexistent@x.com')
    await page.getByRole('button', { name: '查询' }).click()

    await page.getByRole('button', { name: '重置' }).click()

    await expect(page.getByPlaceholder('按邮箱模糊搜索')).toHaveValue('')
    await expect(page.locator('.admin-users-filters').getByPlaceholder('按用户 ID 精确查询')).toHaveValue('')
  })

  test('无结果查询 - 不存在的邮箱时表格无该行', async ({ page }) => {
    await loginAsAdmin(page)
    const fakeEmail = `no-such-user-${Date.now()}@example.com`
    await page.getByPlaceholder('按邮箱模糊搜索').fill(fakeEmail)
    await page.getByRole('button', { name: '查询' }).click()

    await expect(page.getByRole('row').filter({ hasText: fakeEmail })).toHaveCount(0)
  })
})

// ---------------------------------------------------------------------------
// 查询条件：单条件、组合条件、边界
// ---------------------------------------------------------------------------
test.describe('Admin 用户管理 - 查询条件与组合', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('单条件 - 按姓名模糊查询能命中', async ({ page }) => {
    const unique = `name${Date.now()}`
    const email = `e2e-name-q-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill(`张三-${unique}`)
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按姓名模糊搜索').fill(unique)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: unique })).toBeVisible()
  })

  test('单条件 - 按设备 Token 模糊查询能命中', async ({ page }) => {
    const unique = `dt${Date.now()}`
    const email = `e2e-dt-q-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('DeviceUser')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByLabel('设备 Token').fill(`token-${unique}-suffix`)
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.locator('.admin-users-filters').getByPlaceholder('按设备 Token 模糊搜索').fill(unique)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })

  test('空条件点查询 - 不报错且返回列表', async ({ page }) => {
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.locator('.el-table')).toBeVisible()
    await expect(page.getByText('加载用户列表失败')).not.toBeVisible()
  })

  test('组合 - 邮箱+姓名同时满足时命中', async ({ page }) => {
    const namePart = `combo${Date.now()}`
    const email = `e2e-combo-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill(namePart)
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByPlaceholder('按姓名模糊搜索').fill(namePart)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email }).filter({ hasText: namePart })).toBeVisible()
  })

  test('组合 - 邮箱对但姓名不匹配时无结果', async ({ page }) => {
    const email = `e2e-combo-nomatch-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('RealName')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByPlaceholder('按姓名模糊搜索').fill('WrongNameNotExist')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toHaveCount(0)
  })

  test('组合 - 邮箱+设备 Token 同时满足时命中', async ({ page }) => {
    const tokenPart = `tcombo${Date.now()}`
    const email = `e2e-tcombo-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TCombo')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByLabel('设备 Token').fill(`dev-${tokenPart}`)
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.locator('.admin-users-filters').getByPlaceholder('按设备 Token 模糊搜索').fill(tokenPart)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })

  test('组合 - 邮箱对但设备 Token 不匹配时无结果', async ({ page }) => {
    const email = `e2e-tnomatch-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TNoMatch')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.locator('.admin-users-filters').getByPlaceholder('按设备 Token 模糊搜索').fill('nonexistent-token-xyz')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toHaveCount(0)
  })

  test('边界 - 不存在的 ID 精确查询无结果', async ({ page }) => {
    await page.locator('.admin-users-filters').getByPlaceholder('按用户 ID 精确查询').fill('u00000000')
    await page.getByRole('button', { name: '查询' }).click()
    const table = page.locator('.el-table tbody')
    await expect(table.getByRole('row').filter({ hasText: 'u00000000' })).toHaveCount(0)
  })

  test('边界 - 邮箱只输部分（模糊）能命中', async ({ page }) => {
    const email = `e2e-fuzzy-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('Fuzzy')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill('e2e-fuzzy')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })

  // ---------- 创建时间范围查询 ----------
  test('创建时间 - 范围包含该用户时能命中', async ({ page }) => {
    const email = `e2e-time-hit-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TimeHit')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()
    const createdAt = new Date()

    const start = new Date(createdAt.getTime() - 5 * 60 * 1000)
    const end = new Date(createdAt.getTime() + 5 * 60 * 1000)
    await page.locator('.admin-users-filters').getByPlaceholder('开始时间').click()
    const startInput = page.locator('.admin-users-filters input').nth(4)
    const endInput = page.locator('.admin-users-filters input').nth(5)
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })

  test('创建时间 - 范围完全在创建时间之后时无结果', async ({ page }) => {
    const email = `e2e-time-after-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TimeAfter')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()
    const createdAt = new Date()

    const start = new Date(createdAt.getTime() + 24 * 60 * 60 * 1000)
    const end = new Date(createdAt.getTime() + 48 * 60 * 60 * 1000)
    await page.locator('.admin-users-filters').getByPlaceholder('开始时间').click()
    const startInput = page.locator('.admin-users-filters input').nth(4)
    const endInput = page.locator('.admin-users-filters input').nth(5)
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toHaveCount(0)
  })

  test('创建时间 - 范围完全在创建时间之前时无结果', async ({ page }) => {
    const email = `e2e-time-before-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TimeBefore')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()
    const createdAt = new Date()

    const end = new Date(createdAt.getTime() - 60 * 60 * 1000)
    const start = new Date(createdAt.getTime() - 48 * 60 * 60 * 1000)
    await page.locator('.admin-users-filters').getByPlaceholder('开始时间').click()
    const startInput = page.locator('.admin-users-filters input').nth(4)
    const endInput = page.locator('.admin-users-filters input').nth(5)
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toHaveCount(0)
  })

  test('创建时间 - 时间范围与邮箱组合同时满足时命中', async ({ page }) => {
    const email = `e2e-time-combo-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TimeCombo')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()
    const createdAt = new Date()

    const start = new Date(createdAt.getTime() - 2 * 60 * 1000)
    const end = new Date(createdAt.getTime() + 2 * 60 * 1000)
    await page.locator('.admin-users-filters').getByPlaceholder('开始时间').click()
    const startInput = page.locator('.admin-users-filters input').nth(4)
    const endInput = page.locator('.admin-users-filters input').nth(5)
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })

  test('创建时间 - 时间范围对但邮箱不匹配时无结果', async ({ page }) => {
    const email = `e2e-time-email-nomatch-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TimeEmailNoMatch')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()
    const createdAt = new Date()

    const start = new Date(createdAt.getTime() - 5 * 60 * 1000)
    const end = new Date(createdAt.getTime() + 5 * 60 * 1000)
    await page.locator('.admin-users-filters').getByPlaceholder('开始时间').click()
    const startInput = page.locator('.admin-users-filters input').nth(4)
    const endInput = page.locator('.admin-users-filters input').nth(5)
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill('other-not-exist@x.com')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toHaveCount(0)
  })

  test('创建时间 - 不选时间只填其他条件时正常查', async ({ page }) => {
    const email = `e2e-time-empty-${Date.now()}@example.com`
    await page.getByRole('button', { name: '新建用户' }).click()
    const dialog = page.getByRole('dialog', { name: '新建用户' })
    await dialog.getByLabel('姓名').fill('TimeEmpty')
    await dialog.getByLabel('邮箱').fill(email)
    await dialog.getByLabel('密码').fill('Pass123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(page.getByText('创建用户成功')).toBeVisible()

    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()
  })
})
