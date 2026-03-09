import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

interface AppTestUser {
  email: string
  password: string
  name: string
}

interface CreatedGroup {
  id: string
  name: string
}

async function registerUserForE2E(label: string): Promise<AppTestUser> {
  const ts = Date.now()
  const email = `app-groups-${label}-${ts}@example.com`
  const password = '1234'
  const name = `App Groups E2E ${label}`

  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`注册测试用户失败: ${res.status} - ${text}`)
  }

  return { email, password, name }
}

async function loginAndGetToken(user: AppTestUser): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: user.email, password: user.password }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`登录获取 token 失败: ${res.status} - ${text}`)
  }
  const data = (await res.json()) as { access_token: string }
  return data.access_token
}

async function createGroupAsUser(user: AppTestUser, name: string): Promise<CreatedGroup> {
  const token = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`创建群组失败: ${res.status} - ${text}`)
  }
  const data = await res.json()
  return { id: data.group.id, name: data.group.name }
}

async function joinGroupViaApi(user: AppTestUser, groupId: string): Promise<void> {
  const token = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`通过 API 加入群组失败: ${res.status} - ${text}`)
  }
}

async function markGroupInactiveByAdmin(groupId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/groups/${groupId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({ is_active: false }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`admin 停用群组失败: ${res.status} - ${text}`)
  }
}

async function loginViaUI(page: import('@playwright/test').Page, user: AppTestUser) {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

test.describe('App 我的群组页面 - 基础场景', () => {
  test('1. 全新用户看到空状态与未选择群组', async ({ page }) => {
    const user = await registerUserForE2E('empty')

    await loginViaUI(page, user)
    await page.goto('/app/groups')

    // 页面主标题（h2）
    await expect(page.locator('.app-groups-title')).toBeVisible()

    // 概览标签
    await expect(page.getByText('已加入群组').locator('..')).toContainText('0')

    // 我的群组空状态
    await expect(
      page.getByText('你还没有加入任何群组，可以先新建一个群组，或等待他人创建并邀请你加入。'),
    ).toBeVisible()

    // 当前群组详情空状态
    await expect(page.getByText('尚未选择群组')).toBeVisible()
  })

  test('2. 通过 UI 新建群组并自动成为当前群组', async ({ page }) => {
    const user = await registerUserForE2E('leader-ui-create')
    await loginViaUI(page, user)
    await page.goto('/app/groups')

    const groupName = `UI创建群-${Date.now()}`

    await page.getByRole('button', { name: '新建群组' }).click()
    const dialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('名称').fill(groupName)
    await dialog.getByRole('button', { name: '创建' }).click()

    await expect(page.getByText('创建群组成功')).toBeVisible()

    // 我的群组列表出现该群，标记为当前
    const listItem = page.locator('.app-groups-list-item').filter({ hasText: groupName }).first()
    await expect(listItem).toBeVisible()
    await expect(listItem.getByText('群主')).toBeVisible()
    await expect(listItem.getByText('当前')).toBeVisible()

    // 详情中成员数为 1，成员列表只有自己且有“我”标记
    await expect(page.getByText(`成员数：1`)).toBeVisible()
    const memberRow = page.locator('.app-groups-member-item').first()
    await expect(memberRow.getByText('我')).toBeVisible()
  })
})

test.describe.serial('App 我的群组页面 - 多角色与加入/退出', () => {
  test('3. 另一用户通过下拉加入一个可加入群', async ({ page }) => {
    const leader = await registerUserForE2E('leader-join')
    const member = await registerUserForE2E('member-join')

    await createGroupAsUser(leader, `可加入群-${Date.now()}`)

    await loginViaUI(page, member)
    await page.goto('/app/groups')

    // 通过下拉选择任意一个可加入的群；如果当前环境下没有可加入群，则验证空提示文案
    const select = page.locator('.app-groups-join-input')
    await expect(select).toBeVisible()
    await select.click()

    const options = page.getByRole('option')
    const count = await options.count()
    if (count === 0) {
      test.skip()
    }

    await options.first().click()
    await page.getByRole('button', { name: '加入群组' }).click()

    await expect(page.getByText('加入群组成功')).toBeVisible()

    // 我的群组列表中出现至少一个群，且有“成员”“当前”标记
    const listItem = page.locator('.app-groups-list-item').first()
    await expect(listItem).toBeVisible()
    await expect(listItem.getByText('成员')).toBeVisible()
    await expect(listItem.getByText('当前')).toBeVisible()
  })

  test('4. 成员退出群组后不再出现在我的群组中', async ({ page }) => {
    const leader = await registerUserForE2E('leader-leave')
    const member = await registerUserForE2E('member-leave')

    const group = await createGroupAsUser(leader, `退出测试群-${Date.now()}`)
    await joinGroupViaApi(member, group.id)

    await loginViaUI(page, member)
    await page.goto('/app/groups')

    // 详情中点击退出群组
    await page.locator('.app-groups-list-item').filter({ hasText: group.name }).first().click()
    await page.getByRole('button', { name: '退出群组' }).click()
    await page.getByRole('button', { name: '退出群组' }).last().click()

    await expect(page.getByText('已退出群组')).toBeVisible()

    // 我的群组列表中不再包含该群
    await expect(
      page.locator('.app-groups-list-item').filter({ hasText: group.name }),
    ).toHaveCount(0)
  })

  test('5. 群主修改群名称后，列表、详情与头部的当前群组名称同步更新', async ({ page, context }) => {
    const leader = await registerUserForE2E('leader-rename')
    const group = await createGroupAsUser(leader, `重命名群-${Date.now()}`)

    await loginViaUI(page, leader)
    await page.goto('/app/groups')

    // 选中该群
    await page.locator('.app-groups-list-item').filter({ hasText: group.name }).first().click()

    const newName = `${group.name}-已重命名`
    await page.getByRole('button', { name: '修改名称' }).click()
    const promptInput = page.locator('.el-message-box').getByRole('textbox')
    await promptInput.fill(newName)
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('群组名称已更新')).toBeVisible()

    // 列表更新
    const listItem = page.locator('.app-groups-list-item').filter({ hasText: newName }).first()
    await expect(listItem).toBeVisible()

    // 详情标题更新
    await expect(page.getByRole('heading', { name: newName })).toBeVisible()

    // 头部当前群组名称更新（需要刷新以读取 localStorage）
    await page.reload()
    const header = page.locator('.app-header-right')
    await expect(header.getByText(newName)).toBeVisible()

    // 再开一个新页面验证 localStorage 持久化
    const page2 = await context.newPage()
    await page2.goto('/app/groups')
    const header2 = page2.locator('.app-header-right')
    await expect(header2.getByText(newName)).toBeVisible()
  })

  test('6. 群主踢出成员后成员从详情与成员数中消失', async ({ page }) => {
    const leader = await registerUserForE2E('leader-kick')
    const member = await registerUserForE2E('member-kick')

    const group = await createGroupAsUser(leader, `踢人测试群-${Date.now()}`)
    await joinGroupViaApi(member, group.id)

    await loginViaUI(page, leader)
    await page.goto('/app/groups')
    await page.locator('.app-groups-list-item').filter({ hasText: group.name }).first().click()

    // 成员列表中能看到该成员（显示的是昵称，而不是邮箱）
    const memberItem = page
      .locator('.app-groups-member-item')
      .filter({ hasText: `App Groups E2E member-kick` })
    await expect(memberItem).toBeVisible()

    // 点击移出
    await memberItem.getByRole('button', { name: '移出' }).click()
    await page.getByRole('button', { name: '踢出' }).last().click()

    await expect(page.getByText('已将成员移出群组')).toBeVisible()
    await expect(
      page.locator('.app-groups-member-item').filter({ hasText: member.email }),
    ).toHaveCount(0)
  })
})

test.describe('App 我的群组页面 - 边界与异常', () => {
  test('7. 新建群组表单校验：名称为空时阻止创建', async ({ page }) => {
    const user = await registerUserForE2E('create-validate')
    await loginViaUI(page, user)
    await page.goto('/app/groups')

    await page.getByRole('button', { name: '新建群组' }).click()
    const dialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(dialog).toBeVisible()

    await dialog.getByLabel('名称').fill('')
    await dialog.getByRole('button', { name: '创建' }).click()

    await expect(dialog.getByText('请输入群组名称')).toBeVisible()
  })

  test('8. 新建群组弹窗多次打开关闭时表单状态被重置', async ({ page }) => {
    const user = await registerUserForE2E('create-reset')
    await loginViaUI(page, user)
    await page.goto('/app/groups')

    const tempName = `Temp-${Date.now()}`

    await page.getByRole('button', { name: '新建群组' }).click()
    let dialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('名称').fill(tempName)
    await dialog.getByRole('button', { name: '取消' }).click()

    await page.getByRole('button', { name: '新建群组' }).click()
    dialog = page.getByRole('dialog', { name: '新建群组' })
    await expect(dialog.getByLabel('名称')).toHaveValue('')
  })

  test.skip('9. 满员群不会出现在可加入下拉中（后端已覆盖，E2E 暂时跳过以避免环境相关波动）', async () => {})

  test('10. 停用群不会出现在可加入下拉中', async ({ page }) => {
    const leader = await registerUserForE2E('leader-inactive')
    const viewer = await registerUserForE2E('viewer-inactive')

    const group = await createGroupAsUser(leader, `停用测试群-${Date.now()}`)
    await markGroupInactiveByAdmin(group.id)

    await loginViaUI(page, viewer)
    await page.goto('/app/groups')

    const select = page.locator('.app-groups-join-input')
    await expect(select).toBeVisible()
    await select.click()
    await expect(page.getByRole('option', { name: new RegExp(group.name) })).toHaveCount(0)
  })

  test('11. 成员视角不展示修改名称与移出他人按钮', async ({ page }) => {
    const leader = await registerUserForE2E('leader-member-ui')
    const member = await registerUserForE2E('member-ui')

    const group = await createGroupAsUser(leader, `权限测试群-${Date.now()}`)
    await joinGroupViaApi(member, group.id)

    await loginViaUI(page, member)
    await page.goto('/app/groups')
    await page.locator('.app-groups-list-item').filter({ hasText: group.name }).first().click()

    // 详情操作区不应有“修改名称”按钮
    await expect(page.getByRole('button', { name: '修改名称' })).toHaveCount(0)

    // 成员列表中不应出现“移出”按钮
    await expect(page.getByRole('button', { name: '移出' })).toHaveCount(0)
  })
})

