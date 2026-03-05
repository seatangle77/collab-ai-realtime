import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

type MembershipItem = {
  id: string
  group_id: string
  user_id: string
  role: string
  status: string
  created_at: string
}

async function loginAsAdminAndGoToMemberships(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto('/admin/memberships')
  await expect(page.getByRole('heading', { name: '成员关系管理' })).toBeVisible()
}

async function registerAndLogin(label: string): Promise<{ userId: string; accessToken: string }> {
  const email = `e2e-membership-${label}-${Date.now()}@example.com`
  const password = 'Pass123!'

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: `成员测试-${label}`,
      email,
      password,
      device_token: `device-membership-${label}`,
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

async function joinGroup(accessToken: string, groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) {
    throw new Error(`join group failed: ${res.status} ${await res.text()}`)
  }
}

async function fetchAdminMembershipsByGroup(groupId: string): Promise<MembershipItem[]> {
  const url = new URL('/api/admin/memberships', API_BASE)
  url.searchParams.set('group_id', groupId)
  url.searchParams.set('page', '1')
  url.searchParams.set('page_size', '50')

  const res = await fetch(url, {
    headers: { 'X-Admin-Token': ADMIN_API_KEY },
  })
  if (!res.ok) {
    throw new Error(`admin list memberships failed: ${res.status} ${await res.text()}`)
  }
  const data = (await res.json()) as { items: MembershipItem[] }
  return data.items
}

async function updateMembershipStatus(id: string, status: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/memberships/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({ status }),
  })
  if (!res.ok) {
    throw new Error(`admin update membership status failed: ${res.status} ${await res.text()}`)
  }
}

async function setupMembershipFixture() {
  const leader = await registerAndLogin('leader')
  const member1 = await registerAndLogin('member1')
  const member2 = await registerAndLogin('member2')

  const { groupId } = await createGroup(leader.accessToken, `成员关系测试群-${Date.now()}`)
  await joinGroup(member1.accessToken, groupId)
  await joinGroup(member2.accessToken, groupId)

  const memberships = await fetchAdminMembershipsByGroup(groupId)
  const createdDates = memberships
    .map((m) => new Date(m.created_at))
    .filter((d) => !Number.isNaN(d.getTime()))

  const earliest = new Date(Math.min(...createdDates.map((d) => d.getTime())))
  const latest = new Date(Math.max(...createdDates.map((d) => d.getTime())))

  return {
    groupId,
    leaderUserId: leader.userId,
    member1UserId: member1.userId,
    member2UserId: member2.userId,
    memberships,
    earliestCreatedAt: earliest,
    latestCreatedAt: latest,
  }
}

const shared: {
  groupId: string
  leaderUserId: string
  member1UserId: string
  member2UserId: string
  memberships: MembershipItem[]
  earliestCreatedAt: Date
  latestCreatedAt: Date
} = {} as any

test.describe.serial('Admin 成员关系管理页面 - 查询与时间', () => {
  test.beforeAll(async () => {
    const fixture = await setupMembershipFixture()
    Object.assign(shared, fixture)
  })

  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToMemberships(page)
  })

  test('0. 通过 Admin 页面新建成员关系并在列表中看到', async ({ page }) => {
    // 独立准备一组群组和用户，避免污染 shared fixture
    const leader = await registerAndLogin('ui-create-leader')
    const { groupId } = await createGroup(leader.accessToken, `UI创建成员关系测试群-${Date.now()}`)

    const member = await registerAndLogin('ui-create-member')

    // 打开新建成员关系对话框
    await page.getByRole('button', { name: '新建成员关系' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建成员关系' })
    await expect(createDialog).toBeVisible()

    // 选择群组：下拉+搜索
    const groupSelect = createDialog.locator('.el-form-item').filter({ hasText: '群组 ID' }).locator('.el-select')
    await groupSelect.click()
    const groupOption = page.getByRole('option').filter({ hasText: groupId }).first()
    await groupOption.click()

    // 选择用户：下拉+搜索（列表里包含新建用户）
    const userSelect = createDialog.locator('.el-form-item').filter({ hasText: '用户 ID' }).locator('.el-select')
    await userSelect.click()
    const userOption = page.getByRole('option').filter({ hasText: member.userId }).first()
    await userOption.click()

    await createDialog.getByRole('button', { name: '创建' }).click()

    await expect(page.getByText('创建成员关系成功')).toBeVisible()

    // 按群组 ID + 用户 ID 查询应该能看到该成员关系
    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByPlaceholder('按用户 ID 精确查询').fill(member.userId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: groupId }).filter({ hasText: member.userId })
    await expect(rows.first()).toBeVisible()
  })

  test('1. 按群组 ID 查询出准备好的成员关系', async ({ page }) => {
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(rows.first()).toBeVisible()
  })

  test('2. 按用户 ID 精确查询', async ({ page }) => {
    await page.getByPlaceholder('按用户 ID 精确查询').fill(shared.member1UserId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: shared.member1UserId })
    await expect(rows.first()).toBeVisible()
  })

  test('3. 按成员状态筛选 active/left', async ({ page }) => {
    const member2Membership = shared.memberships.find((m) => m.user_id === shared.member2UserId)
    if (!member2Membership) {
      throw new Error('member2 membership not found in shared fixture')
    }
    await updateMembershipStatus(member2Membership.id, 'left')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)

    await page.locator('.admin-memberships-filters .el-select').first().click()
    await page.getByRole('option', { name: '有效 (active)' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const activeRows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(activeRows.first()).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    await page.locator('.admin-memberships-filters .el-select').first().click()
    await page.getByRole('option', { name: '已退出 (left)' }).click()
    await page.getByRole('button', { name: '查询' }).click()

    const leftRows = page.getByRole('row').filter({ hasText: shared.member2UserId })
    await expect(leftRows.first()).toBeVisible()
  })

  test('4. 按创建时间范围筛选（命中窗口）', async ({ page }) => {
    const start = new Date(shared.earliestCreatedAt.getTime() - 10 * 60 * 1000)
    const end = new Date(shared.latestCreatedAt.getTime() + 10 * 60 * 1000)
    const startStr = start.toISOString().slice(0, 19).replace('T', ' ')
    const endStr = end.toISOString().slice(0, 19).replace('T', ' ')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    const startInput = page.locator('.admin-memberships-filters').getByPlaceholder('开始时间')
    const endInput = page.locator('.admin-memberships-filters').getByPlaceholder('结束时间')
    await startInput.click()
    await startInput.fill(startStr)
    await endInput.fill(endStr)

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()
    const rows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(rows.first()).toBeVisible()
  })

  test('5. 创建时间范围在未来查不到准备阶段的成员关系', async ({ page }) => {
    const base = shared.latestCreatedAt
    const futureStart = new Date(base.getTime() + 60 * 60 * 1000)
    const futureEnd = new Date(base.getTime() + 2 * 60 * 60 * 1000)
    const startStr = futureStart.toISOString().slice(0, 19).replace('T', ' ')
    const endStr = futureEnd.toISOString().slice(0, 19).replace('T', ' ')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(shared.groupId)
    const startInput = page.locator('.admin-memberships-filters').getByPlaceholder('开始时间')
    const endInput = page.locator('.admin-memberships-filters').getByPlaceholder('结束时间')
    await startInput.click()
    await startInput.fill(startStr)
    await endInput.fill(endStr)

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()
    const rows = page.getByRole('row').filter({ hasText: shared.groupId })
    await expect(rows).toHaveCount(0)
  })
})

test.describe('Admin 成员关系管理 - 查询组合与时间边界', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToMemberships(page)
  })

  test('查询组合 - 群组 ID + 用户 ID + 状态', async ({ page }) => {
    const fixture = await setupMembershipFixture()
    const targetMembership = fixture.memberships.find((m) => m.user_id === fixture.member1UserId) ?? fixture.memberships[0]

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)
    await page.getByPlaceholder('按用户 ID 精确查询').fill(targetMembership.user_id)

    await page.locator('.admin-memberships-filters .el-select').first().click()
    await page.getByRole('option', { name: targetMembership.status === 'active' ? '有效 (active)' : '已退出 (left)' }).click()

    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: fixture.groupId }).filter({ hasText: targetMembership.user_id })
    await expect(rows.first()).toBeVisible()
  })

  test('创建时间仅设置开始或结束也能查到记录', async ({ page }) => {
    const fixture = await setupMembershipFixture()
    const createdDates = fixture.memberships.map((m) => new Date(m.created_at)).filter((d) => !Number.isNaN(d.getTime()))
    const earliest = new Date(Math.min(...createdDates.map((d) => d.getTime())))
    const latest = new Date(Math.max(...createdDates.map((d) => d.getTime())))

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)

    const startInput = page.locator('.admin-memberships-filters').getByPlaceholder('开始时间')
    const endInput = page.locator('.admin-memberships-filters').getByPlaceholder('结束时间')

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
    const fixture = await setupMembershipFixture()
    const target = fixture.memberships[0]
    const createdAt = new Date(target.created_at)
    const boundary = createdAt.toISOString().slice(0, 19).replace('T', ' ')

    await page.getByPlaceholder('按群组 ID 精确查询').fill(fixture.groupId)
    const startInput = page.locator('.admin-memberships-filters').getByPlaceholder('开始时间')
    const endInput = page.locator('.admin-memberships-filters').getByPlaceholder('结束时间')
    await startInput.click()
    await startInput.fill(boundary)
    await endInput.fill(boundary)

    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: fixture.groupId })
    await expect(rows.first()).toBeVisible()
  })

  test('新建成员关系 - 必填项为空时表单校验阻止创建', async ({ page }) => {
    await page.getByRole('button', { name: '新建成员关系' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建成员关系' })
    await expect(createDialog).toBeVisible()

    // 不选择任何群组和用户，直接点击创建
    await createDialog.getByRole('button', { name: '创建' }).click()

    await expect(createDialog.getByText('请输入群组 ID')).toBeVisible()
    await expect(createDialog.getByText('请输入用户 ID')).toBeVisible()
    await expect(createDialog).toBeVisible()
  })

  test('新建成员关系 - 取消创建时不应产生新数据', async ({ page }) => {
    // 准备一组群组和用户，但只用于校验不会在列表中出现
    const leader = await registerAndLogin('ui-cancel-leader')
    const { groupId } = await createGroup(leader.accessToken, `UI取消创建测试群-${Date.now()}`)
    const member = await registerAndLogin('ui-cancel-member')

    await page.getByRole('button', { name: '新建成员关系' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建成员关系' })
    await expect(createDialog).toBeVisible()

    // 选择群组和用户，但点击取消
    const groupSelect = createDialog.locator('.el-form-item').filter({ hasText: '群组 ID' }).locator('.el-select')
    await groupSelect.click()
    await page.getByRole('option').filter({ hasText: groupId }).first().click()

    const userSelect = createDialog.locator('.el-form-item').filter({ hasText: '用户 ID' }).locator('.el-select')
    await userSelect.click()
    await page.getByRole('option').filter({ hasText: member.userId }).first().click()

    await createDialog.getByRole('button', { name: '取消' }).click()

    // 按 groupId + userId 查询，应查不到该成员关系
    await page.getByPlaceholder('按群组 ID 精确查询').fill(groupId)
    await page.getByPlaceholder('按用户 ID 精确查询').fill(member.userId)
    await page.getByRole('button', { name: '查询' }).click()

    const rows = page.getByRole('row').filter({ hasText: groupId }).filter({ hasText: member.userId })
    await expect(rows).toHaveCount(0)
  })

  test('新建成员关系 - 多次打开关闭弹窗时表单状态重置', async ({ page }) => {
    await page.getByRole('button', { name: '新建成员关系' }).click()
    let createDialog = page.getByRole('dialog', { name: '新建成员关系' })
    await expect(createDialog).toBeVisible()

    // 简单选一个选项后取消
    const groupSelect = createDialog.locator('.el-form-item').filter({ hasText: '群组 ID' }).locator('.el-select')
    await groupSelect.click()
    const anyGroupOption = page.getByRole('option').first()
    await anyGroupOption.click()

    await createDialog.getByRole('button', { name: '取消' }).click()

    // 再次打开，新建表单应重置为空/默认值
    await page.getByRole('button', { name: '新建成员关系' }).click()
    createDialog = page.getByRole('dialog', { name: '新建成员关系' })
    await expect(createDialog).toBeVisible()

    await expect(createDialog.getByText('从下拉中选择或搜索群组')).toBeVisible()
    await expect(createDialog.getByText('从下拉中选择或搜索用户')).toBeVisible()
  })
})

