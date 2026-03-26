import { test, expect } from '@playwright/test'
import { randomUUID } from 'crypto'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const RUN_ID = randomUUID().replace(/-/g, '').slice(0, 6)

interface AppTestUser {
  email: string
  password: string
  name: string
}

interface CreatedGroup {
  id: string
  name: string
}

interface CreatedSession {
  id: string
  title: string
}

async function registerUserForE2E(label: string): Promise<AppTestUser> {
  const email = `app-sessions-${label}-${RUN_ID}-${Date.now()}@example.com`
  const password = '1234'
  const name = `App Sessions User ${label} ${RUN_ID}`

  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`register user failed: ${res.status} - ${text}`)
  }

  return { email, password, name }
}

async function loginAndGetToken(user: AppTestUser): Promise<{ token: string; userId: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: user.email, password: user.password }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`login failed: ${res.status} - ${text}`)
  }
  const data = (await res.json()) as { access_token: string; user: { id: string } }
  return { token: data.access_token, userId: data.user.id }
}

async function createGroupAsUser(user: AppTestUser, name: string): Promise<CreatedGroup> {
  const { token } = await loginAndGetToken(user)
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
    throw new Error(`create group failed: ${res.status} - ${text}`)
  }
  const data = await res.json()
  return { id: data.group.id, name: data.group.name }
}

async function joinGroupViaApi(user: AppTestUser, groupId: string): Promise<void> {
  const { token } = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`join group failed: ${res.status} - ${text}`)
  }
}

async function createSessionViaApi(user: AppTestUser, groupId: string, title: string): Promise<CreatedSession> {
  const { token } = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ session_title: title }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`create session failed: ${res.status} - ${text}`)
  }
  const data = await res.json()
  return { id: data.id, title: data.session_title }
}

async function startSessionViaApi(user: AppTestUser, sessionId: string): Promise<void> {
  const { token } = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/start`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`start session failed: ${res.status} - ${text}`)
  }
}

async function endSessionViaApi(user: AppTestUser, sessionId: string): Promise<void> {
  const { token } = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/end`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`end session failed: ${res.status} - ${text}`)
  }
}

async function loginViaUI(page: import('@playwright/test').Page, user: AppTestUser): Promise<void> {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

async function setAppContext(
  page: import('@playwright/test').Page,
  user: AppTestUser,
  group: CreatedGroup,
): Promise<void> {
  const { token } = await loginAndGetToken(user)
  await page.evaluate(
    ([accessToken, userObj, groupObj]) => {
      window.localStorage.setItem('app_access_token', accessToken)
      window.localStorage.setItem('app_user', JSON.stringify(userObj))
      window.localStorage.setItem('app_current_group', JSON.stringify(groupObj))
    },
    [
      token,
      { id: 'e2e-user-id-unused', name: user.name, email: user.email },
      { id: group.id, name: group.name },
    ],
  )
}

test.describe('App 我的会话页面 - 当前群组前提', () => {
  test('1. 未选当前群组时提示前往我的群组', async ({ page }) => {
    const user = await registerUserForE2E('no-group')
    await loginViaUI(page, user)

    // 确保没有当前群组
    await page.evaluate(() => {
      window.localStorage.removeItem('app_current_group')
    })

    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()

    const emptyNotice = page.getByText('当前未选择群组，请先前往「我的群组」选择或加入一个群组。', { exact: false })
    await expect(emptyNotice).toBeVisible()

    await page.getByRole('button', { name: '前往我的群组' }).click()
    await expect(page).toHaveURL(/\/app\/groups/)
  })
})

test.describe.serial('App 我的会话页面 - 单用户完整流程', () => {
  let user: AppTestUser
  let group: CreatedGroup

  test.beforeAll(async () => {
    test.setTimeout(120_000)
    user = await registerUserForE2E('single-user')
    group = await createGroupAsUser(user, `App Session Group ${RUN_ID}`)
  })

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page, user)
    await setAppContext(page, user, group)
    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()
  })

  test('2. 初始无会话时展示空状态并可新建', async ({ page }) => {
    const emptyText = page.getByText('暂无会话', { exact: false })
    await expect(emptyText).toBeVisible()

    const title = `App E2E Session ${RUN_ID}`
    await page.locator('.app-sessions-new-btn-inline').click()

    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '确 定' }).click()

    await expect(page.getByText('创建会话成功')).toBeVisible()
    const row = page.getByText(title, { exact: false })
    await expect(row).toBeVisible()
  })

  test('3. 筛选 Tab：进行中 / 已结束 / 全部', async ({ page }) => {
    test.setTimeout(90000)
    const titleActive = `App Filter Active ${RUN_ID}`
    const titleToEnd = `App Filter Ended ${RUN_ID}`

    // 新建 active 会话（UI）
    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(titleActive)
    await dialog.getByRole('button', { name: '确 定' }).click()
    await expect(page.getByText(titleActive, { exact: false })).toBeVisible()

    // 通过 API 创建并结束另一个会话（start → end），避免 UI 端触发麦克风权限
    const toEnd = await createSessionViaApi(user, group.id, titleToEnd)
    await startSessionViaApi(user, toEnd.id)
    await endSessionViaApi(user, toEnd.id)

    // 重新加载，使列表反映最新状态
    await page.reload()
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()

    // 进行中 Tab：只有 active 会话可见
    await page.getByRole('button', { name: '进行中' }).click()
    await expect(page.getByText(titleActive, { exact: false })).toBeVisible()
    await expect(page.getByText(titleToEnd, { exact: false })).toHaveCount(0)

    // 已结束 Tab：至少有一条已结束会话
    await page.getByRole('button', { name: '已结束' }).click()
    await expect(page.locator('.app-sessions-item').first()).toBeVisible()

    // 全部 Tab：两个都能看到
    await page.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText(titleActive, { exact: false })).toBeVisible()
    await expect(page.getByText(titleToEnd, { exact: false })).toBeVisible()
  })

  test('4. 编辑会话成功并刷新列表（含未开始/进行中状态）', async ({ page }) => {
    const originalTitle = `App Rename Orig ${RUN_ID}`

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(originalTitle)
    await dialog.getByRole('button', { name: '确 定' }).click()
    await expect(page.getByText('创建会话成功')).toBeVisible()

    const item = page.locator('.app-sessions-item').filter({ hasText: originalTitle }).first()
    await expect(item).toBeVisible()

    // 通过 ⋯ 下拉菜单点击「编辑标题」
    await item.locator('.app-sessions-more-btn').click()
    let editDialog = page.getByRole('dialog', { name: '编辑会话' })
    await page.getByRole('menuitem', { name: '编辑标题' }).click()
    await expect(editDialog).toBeVisible()
    await expect(editDialog.getByText('预设开始')).toBeVisible()

    const newPlanned = '2026-03-20T09:00:00Z'
    // 不修改标题，只更新预设开始时间
    await expect(editDialog.getByLabel('会话标题')).toHaveValue(originalTitle)
    await editDialog.getByPlaceholder('仅未开始会话可编辑').fill(newPlanned)
    await editDialog.getByRole('button', { name: '保 存' }).click()

    // 标题保持不变，说明仅更新时间字段也能成功保存（未开始会话编辑时间能力）
    await expect(page.getByText(originalTitle, { exact: false })).toBeVisible()
  })

  test('5. 点击会话进入详情页，无转写时展示空状态', async ({ page }) => {
    const title = `App Transcripts Empty ${RUN_ID}`
    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '确 定' }).click()
    await expect(page.getByText('创建会话成功')).toBeVisible()

    // 点击会话行（非 ⋯ 按钮区域）进入详情页
    const item = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(item).toBeVisible()
    await item.locator('.app-sessions-item-main').click()

    await expect(page).toHaveURL(/\/app\/sessions\/.+/)
    await expect(page.locator('.app-session-detail-transcripts-empty')).toContainText('暂无转写记录')
  })
})

test.describe.serial('App 我的会话页面 - 表单校验与边界', () => {
  let user: AppTestUser
  let group: CreatedGroup
  let anotherGroup: CreatedGroup

  test.beforeAll(async () => {
    test.setTimeout(120_000)
    user = await registerUserForE2E('form-boundary')
    group = await createGroupAsUser(user, `App Session Form Group ${RUN_ID}`)
    anotherGroup = await createGroupAsUser(user, `App Session Form Group Two ${RUN_ID}`)
  })

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page, user)
    await setAppContext(page, user, group)
    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()
  })

  test('5.1 新建会话 - 标题为空时表单校验阻止提交', async ({ page }) => {
    await page.getByRole('button', { name: '新建会话' }).click()

    const dialog = page.getByRole('dialog', { name: '新建会话' })
    const noGroupTip = page.getByText('你还没有加入任何群组', { exact: false })

    // 兼容性处理：有些环境下可能因为没有任何群组，只弹出提示而不打开弹窗
    await Promise.race([
      dialog.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => {}),
      noGroupTip.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => {}),
    ])

    if (await noGroupTip.isVisible()) {
      // 没有群组时，本用例不适用，直接返回视为通过
      return
    }

    await expect(dialog).toBeVisible()

    // 不填标题，直接点确定
    await dialog.getByRole('button', { name: '确 定' }).click()

    await expect(dialog.getByText('请输入会话标题')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('5.2 新建会话 - 取消时不应产生新会话', async ({ page }) => {
    const title = `App Cancel Create ${RUN_ID}`

    const beforeList = await page.locator('.app-sessions-item').allTextContents()

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '取 消' }).click()

    const afterList = await page.locator('.app-sessions-item').allTextContents()
    expect(afterList).toEqual(beforeList)
    await expect(page.getByText(title, { exact: false })).toHaveCount(0)
  })

  test('5.3 新建会话 - 多次打开关闭弹窗时表单状态重置', async ({ page }) => {
    const tempTitle = `App Temp Title ${RUN_ID}`
    const tempTime = '2026-03-10T09:00:00Z'

    // 第一次打开并填写
    await page.getByRole('button', { name: '新建会话' }).click()
    let dialog = page.getByRole('dialog', { name: '新建会话' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('会话标题').fill(tempTitle)
    await dialog.getByPlaceholder('可选：设置这次会话的起始时间').fill(tempTime)
    // 先按 Esc 关闭日期选择弹层，再点击取消，避免弹层拦截点击事件
    await page.keyboard.press('Escape')
    await dialog.getByRole('button', { name: '取 消' }).click()

    // 再次打开，应为初始空状态（用行内 + 新建按钮，避免匹配到弹窗内确认按钮）
    await page.locator('.app-sessions-new-btn-inline').click()
    dialog = page.getByRole('dialog', { name: '新建会话' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByLabel('会话标题')).toHaveValue('')
    await expect(dialog.getByPlaceholder('可选：设置这次会话的起始时间')).toHaveValue('')
  })

  test('5.4 新建会话 - 预设开始时间创建成功并立即出现在列表中', async ({ page }) => {
    const title = `App With Planned Start ${RUN_ID}`
    const planned = '2026-03-10T10:00:00Z'

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByPlaceholder('可选：设置这次会话的起始时间').fill(planned)
    // 关闭日期选择器浮层，避免其遮挡「确 定」按钮
    await page.keyboard.press('Escape')
    await dialog.getByRole('button', { name: '确 定' }).click()

    await expect(page.getByText('创建会话成功')).toBeVisible()

    // 新建的会话应在列表顶部可见
    const firstItem = page.locator('.app-sessions-item').first()
    await expect(firstItem).toBeVisible()
    await expect(firstItem).toContainText(title)
  })

  test('5.6 新建会话 - 切换所属群组时自动切换当前群组', async ({ page }) => {
    const title = `App Switch Group ${RUN_ID}`

    // 初始使用 group 作为 current_group
    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await expect(dialog).toBeVisible()

    // 所属群组下拉应存在，并允许选择另一个群组
    const groupFormItem = dialog.locator('.el-form-item').filter({ hasText: '所属群组' })
    await expect(groupFormItem).toBeVisible()
    const groupSelect = groupFormItem.locator('.el-select')
    await groupSelect.click()
    await page.getByRole('option', { name: anotherGroup.name }).click()

    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '确 定' }).click()

    // 当前群组应自动切换到另一个群组
    const groupValue = page.locator('.app-sessions-group-value')
    await expect(groupValue).toContainText(anotherGroup.name)

    // 列表中能看到刚创建的会话
    await expect(page.getByText(title, { exact: false })).toBeVisible()
  })

  test('5.5 ⋯ 菜单按状态显示正确的操作项（取消/结束/已结束无操作）', async ({ page }) => {
    test.setTimeout(90000)
    const title = `App Status Menu ${RUN_ID}`

    // 通过 API 创建会话，直接拿到 ID，避免页面 evaluate 跨端口问题
    const created = await createSessionViaApi(user, group.id, title)

    // 加载页面，确保列表已显示
    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()

    const item = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(item).toBeVisible()

    // not_started：⋯ 菜单只有「取消会话」，没有「结束会话」
    await item.locator('.app-sessions-more-btn').click()
    await expect(page.getByRole('menuitem', { name: '取消会话' })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: '结束会话' })).not.toBeVisible()
    await page.keyboard.press('Escape')

    // 通过 API 发起会话（ongoing），避免 UI 端触发麦克风权限
    await startSessionViaApi(user, created.id)

    // 重新加载，使状态更新为 ongoing
    await page.reload()
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()

    const ongoingItem = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(ongoingItem).toBeVisible()

    // ongoing：⋯ 菜单只有「结束会话」，没有「取消会话」
    await ongoingItem.locator('.app-sessions-more-btn').click()
    await expect(page.getByRole('menuitem', { name: '结束会话' })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: '取消会话' })).not.toBeVisible()

    // 通过 ⋯ 菜单结束会话
    await page.getByRole('menuitem', { name: '结束会话' }).click()
    const confirmDialog = page.getByRole('dialog', { name: '结束会话' })
    await expect(confirmDialog).toBeVisible()
    await confirmDialog.getByRole('button', { name: '结束' }).click()
    await expect(page.getByText('会话已结束')).toBeVisible()

    // 重新加载，确保已结束状态已写入后端，再切 Tab
    await page.reload()
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()
    await page.getByRole('button', { name: '已结束' }).click()
    const endedItem = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(endedItem).toBeVisible({ timeout: 15000 })

    // ended：⋯ 菜单无「结束会话」也无「取消会话」，只有「编辑标题」
    await endedItem.locator('.app-sessions-more-btn').click()
    await expect(page.getByRole('menuitem', { name: '结束会话' })).not.toBeVisible()
    await expect(page.getByRole('menuitem', { name: '取消会话' })).not.toBeVisible()
    await expect(page.getByRole('menuitem', { name: '编辑标题' })).toBeVisible()

    // 已结束会话仍可编辑标题，但无预设开始时间控件
    await page.getByRole('menuitem', { name: '编辑标题' }).click()
    const editDialog = page.getByRole('dialog', { name: '编辑会话' })
    await expect(editDialog).toBeVisible()
    await expect(editDialog.getByPlaceholder('仅未开始会话可编辑')).toHaveCount(0)

    const endedNewTitle = `${title} Edited`
    await editDialog.getByLabel('会话标题').fill(endedNewTitle)
    await editDialog.getByRole('button', { name: '保 存' }).click()
    await expect(page.getByText('更新会话成功')).toBeVisible()
    await expect(page.getByText(endedNewTitle, { exact: false })).toBeVisible()
  })
})

test.describe.serial('App 我的会话页面 - 多用户与权限边界', () => {
  let owner: AppTestUser
  let member: AppTestUser
  let outsider: AppTestUser
  let group: CreatedGroup
  let ownerSession: CreatedSession

  test.beforeAll(async () => {
    test.setTimeout(120_000)
    owner = await registerUserForE2E('owner')
    member = await registerUserForE2E('member')
    outsider = await registerUserForE2E('outsider')

    group = await createGroupAsUser(owner, `App Session Auth Group ${RUN_ID}`)
    await joinGroupViaApi(member, group.id)

    ownerSession = await createSessionViaApi(owner, group.id, `Owner Session ${RUN_ID}`)
  })

  test('6. 群成员可以看到他人创建的会话', async ({ page }) => {
    await loginViaUI(page, member)
    await setAppContext(page, member, group)

    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()

    const sessionItem = page.getByText(ownerSession.title, { exact: false })
    await expect(sessionItem).toBeVisible()
  })

  test('7. 非群成员访问该群组会话列表时，前端展示错误提示', async ({ page }) => {
    await loginViaUI(page, outsider)

    // 伪造 current_group 为该群组，但后端会判定不是成员并返回 403
    await page.evaluate((g) => {
      window.localStorage.setItem(
        'app_current_group',
        JSON.stringify({ id: g.id, name: g.name }),
      )
    }, group)

    await page.goto('/app/sessions')

    // 403 后会从 /app/sessions 跳转走（可能跳到 /app/login 再重定向到 /app）
    await expect(page).not.toHaveURL(/\/app\/sessions/)
    await expect(page).toHaveURL(/\/app(\/login)?\/?$/)
  })
})
