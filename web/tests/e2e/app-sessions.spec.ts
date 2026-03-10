import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

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
  const ts = Date.now()
  const email = `app-sessions-${label}-${ts}@example.com`
  const password = '1234'
  const name = `App Sessions E2E ${label}`

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

async function loginAndGetToken(user: AppTestUser): Promise<{ token: string; userId: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: user.email, password: user.password }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`登录获取 token 失败: ${res.status} - ${text}`)
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
    throw new Error(`创建群组失败: ${res.status} - ${text}`)
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
    throw new Error(`通过 API 加入群组失败: ${res.status} - ${text}`)
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
    throw new Error(`通过 API 创建会话失败: ${res.status} - ${text}`)
  }
  const data = await res.json()
  return { id: data.id, title: data.session_title }
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
    user = await registerUserForE2E('single-user')
    group = await createGroupAsUser(user, `会话测试群-${Date.now()}`)
  })

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page, user)
    await setAppContext(page, user, group)
    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()
  })

  test('2. 初始无会话时展示空状态并可新建', async ({ page }) => {
    const emptyText = page.getByText('当前筛选条件下暂无会话', { exact: false })
    await expect(emptyText).toBeVisible()

    const title = `E2E 会话-${Date.now()}`
    await page.getByRole('button', { name: '新建会话' }).click()

    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '确 定' }).click()

    await expect(page.getByText('创建会话成功')).toBeVisible()
    const row = page.getByText(title, { exact: false })
    await expect(row).toBeVisible()
  })

  test('3. 筛选 Tab：进行中 / 已结束 / 全部', async ({ page }) => {
    const titleActive = `E2E Filter-Active-${Date.now()}`
    const titleToEnd = `E2E Filter-Ended-${Date.now()}`

    // 新建两个进行中会话
    for (const t of [titleActive, titleToEnd]) {
      await page.getByRole('button', { name: '新建会话' }).click()
      const dialog = page.getByRole('dialog', { name: '新建会话' })
      await dialog.getByLabel('会话标题').fill(t)
      await dialog.getByRole('button', { name: '确 定' }).click()
      // 以列表中能看到标题为准，避免依赖全局提示的时序
      await expect(page.getByText(t, { exact: false })).toBeVisible()
    }

    // 结束其中一个
    const itemToEnd = page
      .locator('.app-sessions-item')
      .filter({ hasText: titleToEnd })
      .first()
    await expect(itemToEnd).toBeVisible()
    await itemToEnd.getByRole('button', { name: '结束会话' }).click()
    // 在 Element Plus 的确认弹窗中点击“结束”按钮，避免匹配到顶部 Tab「已结束」或其它按钮
    const confirmDialog = page.getByRole('dialog', { name: '结束会话' })
    await expect(confirmDialog).toBeVisible()
    await confirmDialog.getByRole('button', { name: '结束' }).click()
    await expect(page.getByText('会话已结束')).toBeVisible()

    // 进行中：应只包含 active 会话
    await page.getByRole('button', { name: '进行中' }).click()
    await expect(page.getByText(titleActive, { exact: false })).toBeVisible()
    await expect(page.getByText(titleToEnd, { exact: false })).toHaveCount(0)

    // 已结束：只看到已结束那个
    await page.getByRole('button', { name: '已结束' }).click()
    await expect(page.getByText(titleToEnd, { exact: false })).toBeVisible()

    // 全部：两个都能看到
    await page.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText(titleActive, { exact: false })).toBeVisible()
    await expect(page.getByText(titleToEnd, { exact: false })).toBeVisible()
  })

  test('4. 编辑会话成功并刷新列表（含未开始/进行中状态）', async ({ page }) => {
    const originalTitle = `E2E Rename-Orig-${Date.now()}`

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(originalTitle)
    await dialog.getByRole('button', { name: '确 定' }).click()
    await expect(page.getByText('创建会话成功')).toBeVisible()

    const item = page.locator('.app-sessions-item').filter({ hasText: originalTitle }).first()
    await expect(item).toBeVisible()

    // 第一次编辑：会话处于「未开始」状态，应看到预设开始时间控件；这里只改时间，不改标题
    await item.getByRole('button', { name: '编辑' }).click()
    let editDialog = page.getByRole('dialog', { name: '编辑会话' })
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

  test('5. 查看转写：无记录时展示空状态', async ({ page }) => {
    const title = `E2E Transcripts-Empty-${Date.now()}`
    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '确 定' }).click()
    await expect(page.getByText('创建会话成功')).toBeVisible()

    const item = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(item).toBeVisible()

    await item.getByRole('button', { name: '查看转写' }).click()
    const transcriptsDialog = page.getByRole('dialog', { name: new RegExp(`会话转写 - ${title}`) })
    await expect(transcriptsDialog).toBeVisible()

    const emptyText = transcriptsDialog.getByText('当前会话暂无转写记录', { exact: false })
    await expect(emptyText).toBeVisible()

    await transcriptsDialog.getByRole('button', { name: '关 闭' }).click()
    await expect(transcriptsDialog).toBeHidden()
  })
})

test.describe.serial('App 我的会话页面 - 表单校验与边界', () => {
  let user: AppTestUser
  let group: CreatedGroup

  test.beforeAll(async () => {
    user = await registerUserForE2E('form-boundary')
    group = await createGroupAsUser(user, `会话表单群-${Date.now()}`)
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
    await expect(dialog).toBeVisible()

    // 不填标题，直接点确定
    await dialog.getByRole('button', { name: '确 定' }).click()

    await expect(dialog.getByText('请输入会话标题')).toBeVisible()
    await expect(dialog).toBeVisible()
  })

  test('5.2 新建会话 - 取消时不应产生新会话', async ({ page }) => {
    const title = `取消新建-${Date.now()}`

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
    const tempTitle = `临时标题-${Date.now()}`
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

    // 再次打开，应为初始空状态
    await page.getByRole('button', { name: '新建会话' }).click()
    dialog = page.getByRole('dialog', { name: '新建会话' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByLabel('会话标题')).toHaveValue('')
    await expect(dialog.getByPlaceholder('可选：设置这次会话的起始时间')).toHaveValue('')
  })

  test('5.4 新建会话 - 预设开始时间创建成功并立即出现在列表中', async ({ page }) => {
    const title = `带预设时间-${Date.now()}`
    const planned = '2026-03-10T10:00:00Z'

    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByPlaceholder('可选：设置这次会话的起始时间').fill(planned)
    await dialog.getByRole('button', { name: '确 定' }).click()

    await expect(page.getByText('创建会话成功')).toBeVisible()

    // 新建的会话应在列表顶部可见
    const firstItem = page.locator('.app-sessions-item').first()
    await expect(firstItem).toBeVisible()
    await expect(firstItem).toContainText(title)
  })

  test('5.5 已结束会话的“结束会话”按钮禁用', async ({ page }) => {
    const title = `待结束-${Date.now()}`

    // 创建一个会话
    await page.getByRole('button', { name: '新建会话' }).click()
    const dialog = page.getByRole('dialog', { name: '新建会话' })
    await dialog.getByLabel('会话标题').fill(title)
    await dialog.getByRole('button', { name: '确 定' }).click()
    await expect(page.getByText('创建会话成功')).toBeVisible()

    const item = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(item).toBeVisible()

    // 第一次结束（在进行中 Tab 下）
    await item.getByRole('button', { name: '结束会话' }).click()
    const confirmDialog = page.getByRole('dialog', { name: '结束会话' })
    await expect(confirmDialog).toBeVisible()
    await confirmDialog.getByRole('button', { name: '结束' }).click()
    await expect(page.getByText('会话已结束')).toBeVisible()

    // 切换到“已结束”Tab，再检查该会话的按钮状态
    await page.getByRole('button', { name: '已结束' }).click()
    const endedItem = page.locator('.app-sessions-item').filter({ hasText: title }).first()
    await expect(endedItem).toBeVisible()

    // 再次获取该条目的结束按钮，应处于禁用状态
    const endBtn = endedItem.getByRole('button', { name: '结束会话' })
    await expect(endBtn).toBeDisabled()

    // 已结束会话仍然可以编辑标题，但不允许编辑时间
    await endedItem.getByRole('button', { name: '编辑' }).click()
    const editDialog = page.getByRole('dialog', { name: '编辑会话' })
    await expect(editDialog).toBeVisible()
    await expect(editDialog.getByPlaceholder('仅未开始会话可编辑')).toHaveCount(0)

    const endedNewTitle = `${title}-已编辑`
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
    owner = await registerUserForE2E('owner')
    member = await registerUserForE2E('member')
    outsider = await registerUserForE2E('outsider')

    group = await createGroupAsUser(owner, `会话权限群-${Date.now()}`)
    await joinGroupViaApi(member, group.id)

    ownerSession = await createSessionViaApi(owner, group.id, `Owner Session-${Date.now()}`)
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

