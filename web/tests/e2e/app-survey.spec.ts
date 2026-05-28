import { test, expect, type Page, type Response } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

interface TestUser {
  userId: string
  name: string
  email: string
  password: string
  accessToken: string
}

// ─────────────────────────────────────────────────────────────────
// API helpers
// ─────────────────────────────────────────────────────────────────

async function registerAndLogin(label: string): Promise<TestUser> {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const email = `survey-${label}-${unique}@example.com`
  const password = '1234'
  const name = `Survey ${label} ${unique}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!regRes.ok) throw new Error(`register failed: ${await regRes.text()}`)
  const user = await regRes.json()

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error(`login failed: ${await loginRes.text()}`)
  const loginData = await loginRes.json()

  return { userId: user.id, name, email, password, accessToken: loginData.access_token }
}

async function createGroupAndJoin(): Promise<{ groupId: string; groupName: string; members: TestUser[] }> {
  const leader = await registerAndLogin('leader')
  const member1 = await registerAndLogin('m1')
  const member2 = await registerAndLogin('m2')
  const groupName = `Survey E2E ${Date.now()}`

  const groupRes = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${leader.accessToken}` },
    body: JSON.stringify({ name: groupName }),
  })
  if (!groupRes.ok) throw new Error(`create group failed: ${await groupRes.text()}`)
  const groupId = (await groupRes.json()).group.id

  // 用户端建组不含 condition，需通过 admin API 补设
  const condRes = await fetch(`${API_BASE}/api/admin/groups/${groupId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
    body: JSON.stringify({ condition: 'glasses' }),
  })
  if (!condRes.ok) throw new Error(`set condition failed: ${await condRes.text()}`)

  for (const member of [member1, member2]) {
    const joinRes = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${member.accessToken}` },
    })
    if (!joinRes.ok) throw new Error(`join group failed: ${await joinRes.text()}`)
  }

  return { groupId, groupName, members: [leader, member1, member2] }
}

async function loginViaUI(page: Page, user: TestUser) {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

async function loginAsAdmin(page: Page) {
  await page.goto('/admin/login')
  await page.locator('input[type="password"]').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
}

async function expectOkResponse(responsePromise: Promise<Response>, label: string) {
  const response = await responsePromise
  if (!response.ok()) {
    const body = await response.text().catch(() => '')
    throw new Error(`${label} failed: ${response.status()} ${body}`)
  }
}

async function gotoSurveyPage(page: Page) {
  const metaResponse = page.waitForResponse((res) => res.url().includes('/api/questionnaire/meta'))
  const entryResponse = page.waitForResponse((res) => res.url().includes('/api/questionnaire/me'))

  await page.goto('/app/survey')
  await expect(page.locator('.survey-title')).toBeVisible()
  await expectOkResponse(metaResponse, 'GET /api/questionnaire/meta')
  await expectOkResponse(entryResponse, 'GET /api/questionnaire/me')
  await expect(page.locator('.survey-tabs')).toBeVisible()
}

function surveyTab(page: Page, name: 'SRCC' | 'PCS') {
  return page.locator('.survey-tabs .el-tabs__item').filter({ hasText: name })
}

function visibleSurveyCards(page: Page) {
  return page.locator('.survey-tabs .el-tab-pane:visible .question-card')
}

function visibleSubmitButton(page: Page) {
  return page.locator('.survey-tabs .el-tab-pane:visible .submit-btn')
}

function visibleDrawerPane(page: Page) {
  return page.locator('.el-drawer .el-tab-pane:visible')
}

// 点击某道题的某个分数按钮
async function rateQuestion(page: Page, questionZh: string, score: number) {
  const card = visibleSurveyCards(page).filter({ hasText: questionZh })
  await card.locator('.rating-btn', { hasText: String(score) }).click()
}

// 批量给量表所有题打分（简化：全部打同一个分数）
async function fillAllRatings(page: Page, score: number) {
  const buttons = page.locator('.survey-tabs .el-tab-pane:visible .rating-btn')
  const count = await buttons.count()
  for (let i = 0; i < count; i++) {
    // 每道题有 7 个按钮，只点目标分数那个
    const btn = buttons.nth(i)
    const text = await btn.textContent()
    if (text?.trim() === String(score)) {
      // 检查按钮是否在当前可见区域
      await btn.scrollIntoViewIfNeeded()
      await btn.click()
    }
  }
}

// ─────────────────────────────────────────────────────────────────
// 用户端：填写量表全流程
// ─────────────────────────────────────────────────────────────────

test.describe('用户端量表填写', () => {
  test.describe.configure({ mode: 'serial' })

  test('Tab 结构正确：SRCC 和 PCS 两个 Tab 均可见', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    await loginViaUI(page, members[0])

    await gotoSurveyPage(page)
    await expect(surveyTab(page, 'SRCC')).toBeVisible()
    await expect(surveyTab(page, 'PCS')).toBeVisible()
  })

  test('SRCC：未填完不能提交，填完后提交成功', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    await loginViaUI(page, members[0])
    await gotoSurveyPage(page)

    // 未填完时按钮 disabled
    const submitBtn = visibleSubmitButton(page)
    await expect(submitBtn).toBeDisabled()
    await expect(page.locator('.submit-hint').first()).toBeVisible()

    // 给 SRCC 所有题打 5 分
    // SRCC tab 默认打开，可见 15 道题
    const srccCards = visibleSurveyCards(page)
    const count = await srccCards.count()
    expect(count).toBe(15)

    for (let i = 0; i < 15; i++) {
      const card = srccCards.nth(i)
      await card.locator('.rating-btn', { hasText: '5' }).click()
    }

    // 填完后按钮可用
    await expect(submitBtn).toBeEnabled()

    // 提交
    await submitBtn.click()
    await expect(page.getByText(/已保存 SRCC/)).toBeVisible()

    // 提示跳转到 PCS
    await expect(page.getByText(/请继续填写 PCS/)).toBeVisible()
  })

  test('SRCC 提交后自动切换到 PCS Tab', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    await loginViaUI(page, members[0])
    await gotoSurveyPage(page)

    // 填 SRCC 所有题
    const srccCards = visibleSurveyCards(page)
    for (let i = 0; i < 15; i++) {
      await srccCards.nth(i).locator('.rating-btn', { hasText: '4' }).click()
    }
    await visibleSubmitButton(page).click()
    await expect(page.getByText(/已保存 SRCC/)).toBeVisible()

    // 稍等后 Tab 应切换到 PCS
    await page.waitForTimeout(1200)
    await expect(surveyTab(page, 'PCS')).toHaveClass(/is-active/)
  })

  test('PCS：填写 6 题后提交成功，显示"全部完成"横幅', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    await loginViaUI(page, members[0])
    await gotoSurveyPage(page)

    // 先提交 SRCC
    const srccCards = visibleSurveyCards(page)
    for (let i = 0; i < 15; i++) {
      await srccCards.nth(i).locator('.rating-btn', { hasText: '6' }).click()
    }
    await visibleSubmitButton(page).click()
    await expect(page.getByText(/已保存 SRCC/)).toBeVisible()

    // 切到 PCS Tab
    await surveyTab(page, 'PCS').click()
    const pcsCards = visibleSurveyCards(page)
    const pcsCount = await pcsCards.count()
    expect(pcsCount).toBe(6)

    // 填 PCS
    for (let i = 0; i < 6; i++) {
      await pcsCards.nth(i).locator('.rating-btn', { hasText: '7' }).click()
    }
    const pcsSubmitBtn = visibleSubmitButton(page)
    await expect(pcsSubmitBtn).toBeEnabled()
    await pcsSubmitBtn.click()
    await expect(page.getByText(/已保存 PCS/)).toBeVisible()

    // 全部完成横幅
    await expect(page.locator('.all-done-banner')).toBeVisible()
  })

  test('刷新页面后已填答案自动回填', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    await loginViaUI(page, members[0])
    await gotoSurveyPage(page)

    // 提交 SRCC（全部打 3）
    const srccCards = visibleSurveyCards(page)
    for (let i = 0; i < 15; i++) {
      await srccCards.nth(i).locator('.rating-btn', { hasText: '3' }).click()
    }
    await visibleSubmitButton(page).click()
    await expect(page.getByText(/已保存 SRCC/)).toBeVisible()

    // 刷新
    await page.reload()
    await page.waitForSelector('.survey-tabs .el-tab-pane:visible .question-card')

    // 检查按钮 3 已高亮（active 状态）
    const firstCard = visibleSurveyCards(page).first()
    const activeBtn = firstCard.locator('.rating-btn--active')
    await expect(activeBtn).toHaveText('3')

    // 提交按钮文字变为"更新 SRCC"
    await expect(visibleSubmitButton(page)).toContainText('更新 SRCC')
  })

  test('Tab 上的 ✓ 徽章在提交后出现', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    await loginViaUI(page, members[0])
    await gotoSurveyPage(page)

    // 提交前 SRCC Tab 无徽章
    await expect(page.locator('.tab-badge--done').first()).not.toBeVisible()

    // 提交 SRCC
    const srccCards = visibleSurveyCards(page)
    for (let i = 0; i < 15; i++) {
      await srccCards.nth(i).locator('.rating-btn', { hasText: '5' }).click()
    }
    await visibleSubmitButton(page).click()
    await expect(page.getByText(/已保存 SRCC/)).toBeVisible()

    // SRCC Tab 上出现 ✓
    await expect(page.locator('.tab-badge--done').first()).toBeVisible()
  })
})

// ─────────────────────────────────────────────────────────────────
// 后台管理：量表记录列表 + 删除
// ─────────────────────────────────────────────────────────────────

test.describe('管理员量表记录管理', () => {
  test.describe.configure({ mode: 'serial' })

  async function seedUserSurvey(user: TestUser) {
    const srccRes = await fetch(`${API_BASE}/api/questionnaire/srcc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${user.accessToken}` },
      body: JSON.stringify({ responses: Object.fromEntries(Array.from({ length: 15 }, (_, i) => [`q${i + 1}`, 5]) ) }),
    })
    if (!srccRes.ok) throw new Error(`seed srcc failed: ${srccRes.status} ${await srccRes.text()}`)

    const pcsRes = await fetch(`${API_BASE}/api/questionnaire/pcs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${user.accessToken}` },
      body: JSON.stringify({ responses: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [`q${i + 1}`, 6]) ) }),
    })
    if (!pcsRes.ok) throw new Error(`seed pcs failed: ${pcsRes.status} ${await pcsRes.text()}`)
  }

  test('量表记录列表正确展示用户名、群组、条件和状态', async ({ page }) => {
    const { members, groupName } = await createGroupAndJoin()
    const user = members[0]
    await seedUserSurvey(user)

    await loginAsAdmin(page)
    await page.goto('/admin/questionnaire-entries')
    await expect(page.getByRole('heading', { name: '问卷填写记录' })).toBeVisible()

    // 找到该用户所在行
    const row = page.locator('tr').filter({ hasText: user.name })
    await expect(row).toBeVisible()
    await expect(row.getByText(groupName)).toBeVisible()
    await expect(row.getByText(/完成 15\/15/)).toBeVisible()
    await expect(row.getByText(/完成 6\/6/)).toBeVisible()
  })

  test('点击详情抽屉显示题目和用户作答', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    const user = members[0]
    await seedUserSurvey(user)

    await loginAsAdmin(page)
    await page.goto('/admin/questionnaire-entries')

    // 点击详情按钮
    const row = page.locator('tr').filter({ hasText: user.name })
    await row.getByRole('button', { name: '详情' }).click()

    // 抽屉出现
    await expect(page.locator('.el-drawer')).toBeVisible()
    await expect(page.locator('.el-drawer').getByText(user.name)).toBeVisible()

    // SRCC 内容可见
    await expect(visibleDrawerPane(page).locator('.drawer-dim-label').first()).toBeVisible()
    await expect(visibleDrawerPane(page).locator('.drawer-rating-dot--active').first()).toBeVisible()

    // 切换 PCS Tab
    await page.locator('.el-drawer').getByRole('tab', { name: /PCS/ }).click()
    await expect(visibleDrawerPane(page).locator('.drawer-dim-label').filter({ hasText: '归属感' })).toBeVisible()
    await expect(visibleDrawerPane(page).locator('.drawer-rating-dot--active').first()).toBeVisible()
  })

  test('刷新按钮重新加载最新数据', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    const user = members[0]

    await loginAsAdmin(page)
    await page.goto('/admin/questionnaire-entries')

    // 用户还未填写，检查不在列表里
    const rowBefore = page.locator('tr').filter({ hasText: user.name })
    await expect(rowBefore).not.toBeVisible()

    // 后台直接调接口填写
    await seedUserSurvey(user)

    // 点刷新
    await page.getByRole('button', { name: '刷新' }).click()
    await page.waitForTimeout(500)

    // 现在应该出现
    await expect(page.locator('tr').filter({ hasText: user.name })).toBeVisible()
  })

  test('删除记录后行从列表中消失', async ({ page }) => {
    const { members } = await createGroupAndJoin()
    const user = members[0]
    await seedUserSurvey(user)

    await loginAsAdmin(page)
    await page.goto('/admin/questionnaire-entries')

    const row = page.locator('tr').filter({ hasText: user.name })
    await expect(row).toBeVisible()

    // 点删除按钮
    await row.getByRole('button', { name: '删除' }).click()

    // 确认弹窗
    await expect(page.locator('.el-message-box')).toBeVisible()
    await page.locator('.el-message-box').getByRole('button', { name: '确认删除' }).click()

    // 成功提示
    await expect(page.getByText('已删除')).toBeVisible()

    // 行消失
    await expect(page.locator('tr').filter({ hasText: user.name })).not.toBeVisible()
  })
})
