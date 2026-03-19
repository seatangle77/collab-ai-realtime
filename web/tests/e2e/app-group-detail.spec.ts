import { test, expect } from '@playwright/test'

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
  const email = `app-gd-${label}-${ts}@example.com`
  const password = '1234'
  const name = `GD E2E ${label}`

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

async function createGroupAsUser(token: string, name: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`创建群组失败: ${await res.text()}`)
  const data = await res.json()
  return data.group.id as string
}

async function joinGroupViaApi(token: string, groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`加入群组失败: ${await res.text()}`)
}

async function leaveGroupViaApi(token: string, groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/leave`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`退出群组失败: ${await res.text()}`)
}

async function createSessionViaApi(token: string, groupId: string, title: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ session_title: title }),
  })
  if (!res.ok) throw new Error(`创建会话失败: ${await res.text()}`)
  const data = await res.json()
  return data.id as string
}

async function markGroupInactiveByAdmin(groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/groups/${groupId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
    body: JSON.stringify({ is_active: false }),
  })
  if (!res.ok) throw new Error(`停用群组失败: ${await res.text()}`)
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
// A. 页面基础加载
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppGroupDetail - 基础加载', () => {
  test('A-1: 群主直接访问 /app/groups/:id，显示群名、ID、成员数、"我"标记', async ({ page }) => {
    const leader = await registerAndLogin('a1-leader')
    const groupId = await createGroupAsUser(leader.token, `基础加载测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.locator('.app-group-detail-name')).toBeVisible()
    await expect(page.locator('.app-group-detail-id')).toContainText(groupId)
    await expect(page.locator('.app-group-detail-self-tag')).toBeVisible()
  })

  test('A-2: 成员直接访问 /app/groups/:id，页面正常展示群名和成员列表', async ({ page }) => {
    const leader = await registerAndLogin('a2-leader')
    const member = await registerAndLogin('a2-member')
    const groupId = await createGroupAsUser(leader.token, `成员访问测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)

    await loginViaUI(page, member)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.locator('.app-group-detail-name')).toBeVisible()
    await expect(page.locator('.app-group-detail-member-item').first()).toBeVisible()
  })

  test('A-3: 点击返回按钮跳回 /app/groups', async ({ page }) => {
    const leader = await registerAndLogin('a3-leader')
    const groupId = await createGroupAsUser(leader.token, `返回测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '← 返回我的群组' }).click()
    await expect(page).toHaveURL(/\/app\/groups$/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// B. 从 AppGroups 入口导航
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppGroupDetail - 从 AppGroups 入口', () => {
  test('B-1: 在 AppGroups 选中群后点击"进入群组"跳转到详情页', async ({ page }) => {
    const leader = await registerAndLogin('b1-leader')
    const groupName = `导航测试群-${Date.now()}`
    await createGroupAsUser(leader.token, groupName)

    await loginViaUI(page, leader)
    await page.goto('/app/groups')

    await page.locator('.app-groups-list-item').filter({ hasText: groupName }).first().click()
    await page.getByRole('button', { name: '进入群组' }).click()

    await expect(page).toHaveURL(/\/app\/groups\/.+/)
  })

  test('B-2: 进入详情后点返回，回到 AppGroups', async ({ page }) => {
    const leader = await registerAndLogin('b2-leader')
    const groupId = await createGroupAsUser(leader.token, `返回导航测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '← 返回我的群组' }).click()
    await expect(page).toHaveURL(/\/app\/groups$/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// C. 群主操作（serial，共用 fixture）
// ─────────────────────────────────────────────────────────────────────────────
test.describe.serial('AppGroupDetail - 群主操作', () => {
  let leader: TestUser
  let member: TestUser
  let groupId: string

  test.beforeAll(async () => {
    leader = await registerAndLogin('c-leader')
    member = await registerAndLogin('c-member')
    groupId = await createGroupAsUser(leader.token, `群主操作测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)
  })

  test('C-1: 群主修改群名成功，h2 文字更新', async ({ page }) => {
    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    const newName = `重命名后-${Date.now()}`
    await page.getByRole('button', { name: '修改名称' }).click()
    const promptInput = page.locator('.el-message-box').getByRole('textbox')
    await promptInput.fill(newName)
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('群组名称已更新')).toBeVisible()
    await expect(page.locator('.app-group-detail-name')).toContainText(newName)
  })

  test('C-2: 修改群名 - 名称为空，inputValidator 拦截，名称不变', async ({ page }) => {
    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    const originalName = await page.locator('.app-group-detail-name').textContent()
    await page.getByRole('button', { name: '修改名称' }).click()
    const promptInput = page.locator('.el-message-box').getByRole('textbox')
    await promptInput.fill('')
    await page.locator('.el-message-box').getByRole('button', { name: '保存' }).click()

    // dialog 仍在，校验错误可见
    await expect(page.locator('.el-message-box__errormsg')).toBeVisible()
    await page.locator('.el-message-box').getByRole('button', { name: '取消' }).click()
    await expect(page.locator('.app-group-detail-name')).toContainText(originalName!.trim())
  })

  test('C-3: 修改群名 - 取消，名称不变', async ({ page }) => {
    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    const originalName = await page.locator('.app-group-detail-name').textContent()
    await page.getByRole('button', { name: '修改名称' }).click()
    const promptInput = page.locator('.el-message-box').getByRole('textbox')
    await promptInput.fill(`不会保存的名字-${Date.now()}`)
    await page.locator('.el-message-box').getByRole('button', { name: '取消' }).click()

    await expect(page.locator('.app-group-detail-name')).toContainText(originalName!.trim())
  })

  test('C-4: 群主踢出成员成功，成员消失，成员数 -1', async ({ page }) => {
    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    const memberItem = page
      .locator('.app-group-detail-member-item')
      .filter({ hasText: 'GD E2E c-member' })
    await expect(memberItem).toBeVisible()

    const beforeCount = await page.locator('.app-group-detail-member-item').count()

    await memberItem.getByRole('button', { name: '移出' }).click()
    await page.getByRole('button', { name: '踢出' }).last().click()

    await expect(page.getByText('已将成员移出群组')).toBeVisible()
    await expect(
      page.locator('.app-group-detail-member-item').filter({ hasText: 'GD E2E c-member' }),
    ).toHaveCount(0)
    await expect(page.locator('.app-group-detail-member-item')).toHaveCount(beforeCount - 1)
  })

  test('C-5: 踢出成员 - 取消确认，成员仍在', async ({ page }) => {
    // 重新加入一个新成员用于本用例
    const member2 = await registerAndLogin('c5-member')
    await joinGroupViaApi(member2.token, groupId)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    const memberItem = page
      .locator('.app-group-detail-member-item')
      .filter({ hasText: 'GD E2E c5-member' })
    await expect(memberItem).toBeVisible()

    await memberItem.getByRole('button', { name: '移出' }).click()
    await page.getByRole('button', { name: '取消' }).last().click()

    await expect(memberItem).toBeVisible()
  })

  test('C-6: 群主自身条目无"移出"按钮', async ({ page }) => {
    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    const selfItem = page
      .locator('.app-group-detail-member-item')
      .filter({ hasText: '我' })
    await expect(selfItem).toBeVisible()
    await expect(selfItem.getByRole('button', { name: '移出' })).toHaveCount(0)
  })

  test('C-7: 群主不渲染"退出群组"按钮', async ({ page }) => {
    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.getByRole('button', { name: '退出群组' })).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// D. 成员角色 UI 权限
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppGroupDetail - 成员角色 UI 权限', () => {
  test('D-1: 成员不显示"修改名称"按钮', async ({ page }) => {
    const leader = await registerAndLogin('d1-leader')
    const member = await registerAndLogin('d1-member')
    const groupId = await createGroupAsUser(leader.token, `权限测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)

    await loginViaUI(page, member)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.getByRole('button', { name: '修改名称' })).toHaveCount(0)
  })

  test('D-2: 成员列表没有"移出"按钮', async ({ page }) => {
    const leader = await registerAndLogin('d2-leader')
    const member = await registerAndLogin('d2-member')
    const groupId = await createGroupAsUser(leader.token, `移出权限测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)

    await loginViaUI(page, member)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.getByRole('button', { name: '移出' })).toHaveCount(0)
  })

  test('D-3: 成员退出群组成功，跳回 /app/groups', async ({ page }) => {
    const leader = await registerAndLogin('d3-leader')
    const member = await registerAndLogin('d3-member')
    const groupId = await createGroupAsUser(leader.token, `退出测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)

    await loginViaUI(page, member)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '退出群组' }).click()
    await page.getByRole('button', { name: '退出群组' }).last().click()

    await expect(page).toHaveURL(/\/app\/groups$/)
  })

  test('D-4: 成员退出 - 取消确认，停留在详情页', async ({ page }) => {
    const leader = await registerAndLogin('d4-leader')
    const member = await registerAndLogin('d4-member')
    const groupId = await createGroupAsUser(leader.token, `取消退出测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)

    await loginViaUI(page, member)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '退出群组' }).click()
    await page.getByRole('button', { name: '取消' }).last().click()

    await expect(page).toHaveURL(new RegExp(`/app/groups/${groupId}`))
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// E. 历史会话区
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppGroupDetail - 历史会话区', () => {
  test('E-1: 无会话时显示空状态文案', async ({ page }) => {
    const leader = await registerAndLogin('e1-leader')
    const groupId = await createGroupAsUser(leader.token, `无会话测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.locator('.app-group-detail-sessions-empty')).toBeVisible()
    await expect(page.locator('.app-group-detail-session-item')).toHaveCount(0)
  })

  test.describe('有会话时展示', () => {
    let leader: TestUser
    let groupId: string

    test.beforeAll(async () => {
      leader = await registerAndLogin('e-sessions-leader')
      groupId = await createGroupAsUser(leader.token, `有会话测试群-${Date.now()}`)
      await createSessionViaApi(leader.token, groupId, '测试会话 not_started')
    })

    test('E-2: 有会话时展示会话标题', async ({ page }) => {
      await loginViaUI(page, leader)
      await page.goto(`/app/groups/${groupId}`)

      await expect(page.locator('.app-group-detail-session-item').first()).toBeVisible()
      await expect(page.locator('.app-group-detail-session-title').first()).toContainText('测试会话')
    })
  })

  test('E-4: 点击"发起讨论"按钮，弹窗出现', async ({ page }) => {
    const leader = await registerAndLogin('e4-leader')
    const groupId = await createGroupAsUser(leader.token, `发起讨论测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '发起讨论' }).click()
    await expect(page.getByRole('dialog', { name: '发起讨论' })).toBeVisible()
  })

  test('E-5: 创建会话 - 标题为空，校验阻止', async ({ page }) => {
    const leader = await registerAndLogin('e5-leader')
    const groupId = await createGroupAsUser(leader.token, `校验测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '发起讨论' }).click()
    const dialog = page.getByRole('dialog', { name: '发起讨论' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: '发起' }).click()

    await expect(dialog.getByText('请输入会话标题')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('E-6: 创建会话 - 取消，无新数据，dialog 关闭', async ({ page }) => {
    const leader = await registerAndLogin('e6-leader')
    const groupId = await createGroupAsUser(leader.token, `取消创建会话测试群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '发起讨论' }).click()
    const dialog = page.getByRole('dialog', { name: '发起讨论' })
    await dialog.getByPlaceholder('请输入会话标题').fill('不会保存的标题')
    await dialog.getByRole('button', { name: '取消' }).click()

    await expect(dialog).not.toBeVisible()
    await expect(page.locator('.app-group-detail-sessions-empty')).toBeVisible()
  })

  test('E-7: 创建会话成功，新标题出现，dialog 关闭', async ({ page }) => {
    const leader = await registerAndLogin('e7-leader')
    const groupId = await createGroupAsUser(leader.token, `创建会话成功测试群-${Date.now()}`)
    const newTitle = `新会话标题-${Date.now()}`

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    await page.getByRole('button', { name: '发起讨论' }).click()
    const dialog = page.getByRole('dialog', { name: '发起讨论' })
    await dialog.getByPlaceholder('请输入会话标题').fill(newTitle)
    await dialog.getByRole('button', { name: '发起' }).click()

    await expect(page.getByText('会话创建成功')).toBeVisible()
    await expect(dialog).not.toBeVisible()
    await expect(page.locator('.app-group-detail-session-title').first()).toContainText(newTitle)
  })

  test('E-8: 群组已停用，后端返回 404，页面显示错误状态', async ({ page }) => {
    const leader = await registerAndLogin('e8-leader')
    const groupId = await createGroupAsUser(leader.token, `停用讨论测试群-${Date.now()}`)
    await markGroupInactiveByAdmin(groupId)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    // 后端对已停用群组返回 404，前端显示错误状态
    await expect(page.locator('.app-group-detail-error')).toBeVisible()
    await expect(page.getByRole('button', { name: '返回群组列表' })).toBeVisible()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// F. 边界与异常
// ─────────────────────────────────────────────────────────────────────────────
test.describe('AppGroupDetail - 边界与异常', () => {
  test('F-1: 未登录访问 /app/groups/:id，跳转到登录页', async ({ page }) => {
    await page.goto('/app/groups/ufake00000000')
    await expect(page).toHaveURL(/\/app\/login/)
  })

  test('F-2: 登录后访问不存在的群组 ID，显示错误状态', async ({ page }) => {
    const user = await registerAndLogin('f2-user')
    await loginViaUI(page, user)
    await page.goto('/app/groups/ufake00000000')

    await expect(page.locator('.app-group-detail-error')).toBeVisible()
    await expect(page.getByRole('button', { name: '返回群组列表' })).toBeVisible()
  })

  test('F-3: 已退出群组的用户直接访问该群 URL，显示错误状态', async ({ page }) => {
    const leader = await registerAndLogin('f3-leader')
    const member = await registerAndLogin('f3-member')
    const groupId = await createGroupAsUser(leader.token, `退出后访问测试群-${Date.now()}`)
    await joinGroupViaApi(member.token, groupId)
    await leaveGroupViaApi(member.token, groupId)

    await loginViaUI(page, member)
    await page.goto(`/app/groups/${groupId}`)

    await expect(page.locator('.app-group-detail-error')).toBeVisible()
  })

  test('F-4: 错误状态下点击返回，跳回 /app/groups', async ({ page }) => {
    const user = await registerAndLogin('f4-user')
    await loginViaUI(page, user)
    await page.goto('/app/groups/ufake00000000')

    await expect(page.locator('.app-group-detail-error')).toBeVisible()
    await page.getByRole('button', { name: '返回群组列表' }).click()
    await expect(page).toHaveURL(/\/app\/groups$/)
  })

  test('F-5: 停用群组后端返回 404，页面显示错误状态', async ({ page }) => {
    const leader = await registerAndLogin('f5-leader')
    const groupId = await createGroupAsUser(leader.token, `停用查看测试群-${Date.now()}`)
    await markGroupInactiveByAdmin(groupId)

    await loginViaUI(page, leader)
    await page.goto(`/app/groups/${groupId}`)

    // 后端对已停用群组返回 404，前端显示错误状态
    await expect(page.locator('.app-group-detail-error')).toBeVisible()
    await expect(page.getByRole('button', { name: '返回群组列表' })).toBeVisible()
  })

  test('F-6: password_needs_reset=true 的用户访问详情页，守卫拦截跳改密页', async ({ page }) => {
    const user = await registerAndLogin('f6-user')
    const groupId = await createGroupAsUser(user.token, `改密守卫测试群-${Date.now()}`)
    await markPasswordResetByAdmin(user.userId)

    // 通过 localStorage 注入 token + 标记 needs_reset
    await page.goto('/app/login')
    await page.evaluate(
      ({ token, userId, email }: { token: string; userId: string; email: string }) => {
        localStorage.setItem('app_access_token', token)
        localStorage.setItem(
          'app_user',
          JSON.stringify({ id: userId, email, name: 'f6', password_needs_reset: true }),
        )
      },
      { token: user.token, userId: user.userId, email: user.email },
    )

    await page.goto(`/app/groups/${groupId}`)
    await expect(page).toHaveURL(/\/app\/change-password/)
  })
})
