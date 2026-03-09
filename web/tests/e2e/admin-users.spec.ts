import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await expect(page.getByRole('heading', { name: '用户管理' })).toBeVisible()
}

/** fill 不触发 Vue 的 input，v-model 不更新；填完后触发 input 让 filters 同步，再点查询才带得上条件 */
async function fillEmailSearchAndQuery(page: import('@playwright/test').Page, email: string) {
  const input = page.getByPlaceholder('按邮箱模糊搜索')
  await input.fill(email)
  await input.evaluate((el: HTMLInputElement) => el.dispatchEvent(new Event('input', { bubbles: true })))
  await page.getByRole('button', { name: '查询' }).click()
}

async function createAdminGroupViaApi(name: string): Promise<{ id: string; name: string; created_at: string }> {
  const res = await fetch(`${API_BASE}/api/admin/groups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) {
    throw new Error(`create admin group failed: ${res.status} ${await res.text()}`)
  }
  return (await res.json()) as { id: string; name: string; created_at: string }
}

async function createAdminMembershipViaApi(groupId: string, userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/memberships`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({
      group_id: groupId,
      user_id: userId,
      role: 'member',
      status: 'active',
    }),
  })
  if (!res.ok) {
    throw new Error(`create admin membership failed: ${res.status} ${await res.text()}`)
  }
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
  groupId1: string
  groupName1: string
  groupId2: string
  groupName2: string
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
    // 不依赖列表自动刷新，主动按邮箱查询再断言，避免新用户不在第一页或刷新未完成
    await fillEmailSearchAndQuery(page, shared.email)
    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })
    await expect(row).toContainText(shared.initialName)
    await expect(row).toContainText(shared.initialDeviceToken)
  })

  test('3. 编辑用户', async ({ page }) => {
    await fillEmailSearchAndQuery(page, shared.email)

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })
    // 操作列 fixed="right" 时编辑按钮在另一块表格 DOM 里，不在该 row 内，故在表格内点第一个「编辑」
    await page.locator('.admin-users-table').getByRole('button', { name: '编辑' }).first().click()

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
    await fillEmailSearchAndQuery(page, shared.email)

    const updatedRow = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(updatedRow).toBeVisible({ timeout: 30000 })
    await expect(updatedRow).toContainText(shared.updatedName)
    await expect(updatedRow).toContainText(shared.updatedDeviceToken)

    // 列顺序: 多选(0), ID(1), 姓名(2), 邮箱(3), ...
    const idCell = updatedRow.getByRole('cell').nth(1)
    // show-overflow-tooltip 时 tooltip 的 title 为完整 ID，避免 innerText 被截断
    const title = await idCell.getAttribute('title')
    shared.userId = (title ?? (await idCell.innerText())).trim()
  })

  test('5. 按 ID 精确查询', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    const idInput = page.locator('.admin-users-filters').getByPlaceholder('按用户 ID 精确查询')
    await idInput.fill(shared.userId)
    await page.getByRole('button', { name: '查询' }).click()

    const idRow = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(idRow).toBeVisible({ timeout: 30000 })
  })

  test('6. 通过 Admin API 为该用户创建小组与成员关系，并在列表展示', async ({ page }) => {
    // 创建两个小组，并为当前用户创建 active 成员关系
    const g1Name = `E2E-用户小组-1-${Date.now()}`
    const g2Name = `E2E-用户小组-2-${Date.now()}`
    const g1 = await createAdminGroupViaApi(g1Name)
    const g2 = await createAdminGroupViaApi(g2Name)
    shared.groupId1 = g1.id
    shared.groupName1 = g1.name
    shared.groupId2 = g2.id
    shared.groupName2 = g2.name

    await createAdminMembershipViaApi(shared.groupId1, shared.userId)
    await createAdminMembershipViaApi(shared.groupId2, shared.userId)

    // 通过邮箱筛选该用户，检查小组列内容（pressSequentially 确保触发 v-model）
    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按邮箱模糊搜索').pressSequentially(shared.email)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })

  // 列顺序: 多选(0), ID(1), 姓名(2), 邮箱(3), 设备Token(4), 小组ID(5), 小组名称(6), 创建时间(7), 操作(8)
  const groupIdCell = row.getByRole('cell').nth(5)
  const groupNameCell = row.getByRole('cell').nth(6)
    await expect(groupIdCell).toContainText(shared.groupId1)
    await expect(groupIdCell).toContainText(shared.groupId2)
    await expect(groupNameCell).toContainText(shared.groupName1)
    await expect(groupNameCell).toContainText(shared.groupName2)
  })

  test('7. 按小组 ID 精确查询', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.admin-users-filters').getByPlaceholder('按小组 ID 精确查询').fill(shared.groupId1)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })
    await expect(row).toContainText(shared.groupId1)
  })

  test('8. 按小组名称模糊查询', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    const partName = shared.groupName1.slice(0, 6)
    await page.getByPlaceholder('按小组名称模糊搜索').pressSequentially(partName)
    await page.getByRole('button', { name: '查询' }).click()

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })
    await expect(row).toContainText(shared.groupName1)

  // 负向用例主要在后端测试中覆盖，这里前端只验证“能命中”的场景即可
  })

  test('9. 列表中的创建时间显示为人类可读格式', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    await fillEmailSearchAndQuery(page, shared.email)

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })
  const createdAtCell = row.getByRole('cell').nth(7) // 创建时间列（多选+ID+姓名+邮箱+设备+小组ID+小组名称+创建时间）
    const text = (await createdAtCell.innerText()).trim()

    // 不再是原始 ISO 字符串，而是 yyyy-MM-dd HH:mm:ss 形式
    expect(text).toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)
    expect(text).not.toContain('T')
  })

  test('7. 删除用户', async ({ page }) => {
    await fillEmailSearchAndQuery(page, shared.email)

    const row = page.getByRole('row').filter({ hasText: shared.email }).first()
    await expect(row).toBeVisible({ timeout: 30000 })
    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除用户成功')).toBeVisible()
  })

  test('8. 验证删除后查不到该用户', async ({ page }) => {
    await page.getByRole('button', { name: '重置' }).click()
    await fillEmailSearchAndQuery(page, shared.email)

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

    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
  })

  test('批量删除 - 未选时按钮禁用', async ({ page }) => {
    await loginAsAdmin(page)
    await expect(page.getByRole('button', { name: '批量删除' })).toBeDisabled()
  })

  test('批量删除 - 选中两条用户并删除', async ({ page }) => {
    await loginAsAdmin(page)
    const now = Date.now()
    const email1 = `e2e-batch-del-1-${now}@example.com`
    const email2 = `e2e-batch-del-2-${now}@example.com`
    for (const [email, name] of [[email1, 'Batch1'], [email2, 'Batch2']] as const) {
      await page.getByRole('button', { name: '新建用户' }).click()
      const dialog = page.getByRole('dialog', { name: '新建用户' })
      await dialog.getByLabel('姓名').fill(name)
      await dialog.getByLabel('邮箱').fill(email)
      await dialog.getByLabel('密码').fill('Pass123')
      await dialog.getByRole('button', { name: '创建' }).click()
      await expect(page.getByText('创建用户成功')).toBeVisible()
    }
    await page.getByPlaceholder('按邮箱模糊搜索').fill(`e2e-batch-del`)
    await page.getByRole('button', { name: '查询' }).click()
    const row1 = page.getByRole('row').filter({ hasText: email1 }).first()
    const row2 = page.getByRole('row').filter({ hasText: email2 }).first()
    await expect(row1).toBeVisible({ timeout: 30000 })
    await expect(row2).toBeVisible({ timeout: 30000 })
    await row1.locator('.el-checkbox').first().click()
    await row2.locator('.el-checkbox').first().click()
    const batchDeleteBtn = page.getByRole('button').filter({ hasText: /批量删除\s*[（(]2[）)]/ })
    await expect(batchDeleteBtn).toBeVisible({ timeout: 10000 })
    await batchDeleteBtn.click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 2 条用户')).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: email1 })).toHaveCount(0)
    await expect(page.getByRole('row').filter({ hasText: email2 })).toHaveCount(0)
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
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
    await expect(page.getByRole('row').filter({ hasText: unique })).toBeVisible({ timeout: 30000 })
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
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
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
    await expect(page.getByRole('row').filter({ hasText: email }).filter({ hasText: namePart })).toBeVisible({ timeout: 30000 })
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

    await page.getByPlaceholder('按邮箱模糊搜索').pressSequentially(email)
    await page.locator('.admin-users-filters').getByPlaceholder('按设备 Token 模糊搜索').pressSequentially(tokenPart)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
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
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
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

    // 时间窗口放宽到 ±24h，避免时区/延迟导致边界刚好排除该用户
    const start = new Date(createdAt.getTime() - 24 * 60 * 60 * 1000)
    const end = new Date(createdAt.getTime() + 24 * 60 * 60 * 1000)
    const startInput = page.locator('.admin-users-filters').getByPlaceholder('开始')
    const endInput = page.locator('.admin-users-filters').getByPlaceholder('结束')
    await startInput.click()
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
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
    const startInput = page.locator('.admin-users-filters').getByPlaceholder('开始')
    const endInput = page.locator('.admin-users-filters').getByPlaceholder('结束')
    await startInput.click()
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
    const startInput = page.locator('.admin-users-filters').getByPlaceholder('开始')
    const endInput = page.locator('.admin-users-filters').getByPlaceholder('结束')
    await startInput.click()
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

    // 时间窗口放宽到 ±24h，避免时区/时钟差导致刚创建用户被排除在范围外
    const createdAt = new Date()
    const start = new Date(createdAt.getTime() - 24 * 60 * 60 * 1000)
    const end = new Date(createdAt.getTime() + 24 * 60 * 60 * 1000)
    const startInput = page.locator('.admin-users-filters').getByPlaceholder('开始')
    const endInput = page.locator('.admin-users-filters').getByPlaceholder('结束')
    await startInput.click()
    await startInput.fill(start.toISOString().slice(0, 19).replace('T', ' '))
    await endInput.fill(end.toISOString().slice(0, 19).replace('T', ' '))
    await page.getByPlaceholder('按邮箱模糊搜索').fill(email)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
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
    const startInput = page.locator('.admin-users-filters').getByPlaceholder('开始')
    const endInput = page.locator('.admin-users-filters').getByPlaceholder('结束')
    await startInput.click()
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
    await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible({ timeout: 30000 })
  })
})
