import { test, expect, type Page } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const ADMIN_HEADERS = { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY }

// ── helpers ──────────────────────────────────────────────────────────────────

async function registerAndLogin(): Promise<{ userId: string; token: string }> {
  const ts = Date.now()
  const email = `coi-e2e-${ts}@example.com`
  const reg = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `COI E2E ${ts}`, email, password: '1234' }),
  })
  if (!reg.ok) throw new Error(`register failed: ${await reg.text()}`)
  const user = await reg.json()

  const login = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: '1234' }),
  })
  if (!login.ok) throw new Error(`login failed: ${await login.text()}`)
  const { access_token } = await login.json()
  return { userId: user.id, token: access_token }
}

async function seedSession(): Promise<{
  groupName: string
  groupId: string
  sessionTitle: string
  sessionId: string
}> {
  const { userId, token } = await registerAndLogin()
  const ts = Date.now()
  const groupName = `CoI E2E Group ${ts}`
  const sessionTitle = `CoI E2E Session ${ts}`

  const gRes = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name: groupName }),
  })
  if (!gRes.ok) throw new Error(`create group failed: ${await gRes.text()}`)
  const groupId = (await gRes.json()).group.id as string

  const sRes = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ session_title: sessionTitle }),
  })
  if (!sRes.ok) throw new Error(`create session failed: ${await sRes.text()}`)
  const sessionId = (await sRes.json()).id as string

  await fetch(`${API_BASE}/api/sessions/${sessionId}/start`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })

  // 插入 3 条语音转写（先创建完再结束，避免 agent 把测试会话当作真实进行中会话）
  const transcripts = [
    { speaker: '张三', text: '我认为这个方案需要更多的数据支撑才能继续推进。' },
    { speaker: '李四', text: '对，我们可以先从现有的数据库里面找一些相关资料。' },
    { speaker: '王五', text: '那我来负责整理数据部分，大家觉得可以吗？' },
  ]
  for (const tr of transcripts) {
    const r = await fetch(`${API_BASE}/api/admin/transcripts/`, {
      method: 'POST',
      headers: ADMIN_HEADERS,
      body: JSON.stringify({
        session_id: sessionId,
        group_id: groupId,
        user_id: userId,
        speaker: tr.speaker,
        text: tr.text,
        start: '2026-05-01T09:00:00',
        end: '2026-05-01T09:00:05',
        duration: 5.0,
        confidence: 0.95,
      }),
    })
    if (!r.ok) throw new Error(`create transcript failed: ${await r.text()}`)
  }

  // 立即结束会话，避免 agent 把测试会话当作真实进行中会话处理
  await fetch(`${API_BASE}/api/sessions/${sessionId}/end`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })

  return { groupName, groupId, sessionTitle, sessionId }
}

async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
}

/** 通过 data-testid 点开 el-select，等待选项渲染后点击目标选项 */
async function selectElOption(page: Page, testId: string, optionText: string): Promise<void> {
  const select = page.getByTestId(testId)
  await expect(select).toBeVisible()
  await select.click()
  await page.locator('.el-select-dropdown__item:visible').first().waitFor()
  await page.evaluate((name) => {
    const isVisible = (el: Element) => {
      const rect = el.getBoundingClientRect()
      return rect.width > 0 && rect.height > 0
    }
    const dropdowns = Array.from(document.querySelectorAll('.el-select-dropdown')).filter(isVisible)
    const dropdown = dropdowns[dropdowns.length - 1]
    if (!dropdown) throw new Error(`dropdown not found for: ${name}`)
    const option = Array.from(dropdown.querySelectorAll<HTMLElement>('.el-select-dropdown__item')).find(
      (el) => el.textContent?.trim().includes(name) && !el.classList.contains('is-disabled'),
    )
    if (!option) throw new Error(`option not found: ${name}`)
    option.click()
  }, optionText)
  await expect(select).toContainText(optionText)
}

/** 选群组 → 等 session 列表加载完 → 选会话 */
async function selectGroupAndSession(page: Page, groupName: string, sessionTitle: string): Promise<void> {
  await selectElOption(page, 'coi-group-select', groupName)
  await page.waitForTimeout(800)
  await selectElOption(page, 'coi-session-select', sessionTitle)
}

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe('Admin CoI 发言编码页面', () => {
  test('菜单导航到 CoI 发言编码页', async ({ page }) => {
    await loginAsAdmin(page)
    // AdminLayout 菜单项是 div+click，不是 <a>，用 getByText 定位
    await page.getByText('CoI 发言编码').click()
    await expect(page).toHaveURL(/\/admin\/coi-utterances/)
    await expect(page.getByTestId('coi-group-select')).toBeVisible()
    await expect(page.getByTestId('coi-session-select')).toBeVisible()
  })

  test('空状态：未选会话时显示提示', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await expect(page.getByText('请先选择群组和会话')).toBeVisible()
  })

  test('选择群组和会话后可导入转写数据', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')

    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.getByText(/导入成功/)).toBeVisible({ timeout: 8000 })
    await expect(page.locator('.coi-item')).toHaveCount(3)
  })

  test('重复导入显示跳过提示', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)

    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.getByText(/导入成功/)).toBeVisible({ timeout: 8000 })

    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.getByText(/跳过 3 条/)).toBeVisible({ timeout: 8000 })
  })

  test('编辑发言内容和说话人', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await page.locator('.coi-item').first().getByRole('button', { name: '编辑' }).click()

    const speakerInput = page.locator('.coi-item').first().locator('input[placeholder="说话人"]')
    await speakerInput.clear()
    await speakerInput.fill('张三（已修改）')

    const contentInput = page.locator('.coi-item').first().locator('textarea')
    await contentInput.clear()
    await contentInput.fill('这是修改后的发言内容。')

    await page.locator('.coi-item').first().getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('已保存')).toBeVisible()
    await expect(page.locator('.coi-item').first().locator('.speaker-name')).toContainText('张三（已修改）')
    await expect(page.locator('.coi-item').first().locator('.coi-content')).toContainText('这是修改后的发言内容。')
  })

  test('取消编辑不保存', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    const originalText = await page.locator('.coi-item').first().locator('.coi-content').textContent()
    await page.locator('.coi-item').first().getByRole('button', { name: '编辑' }).click()
    await page.locator('.coi-item').first().locator('textarea').fill('取消不会保存的内容')
    await page.locator('.coi-item').first().getByRole('button', { name: '取消' }).click()
    await expect(page.locator('.coi-item').first().locator('.coi-content')).toContainText(originalText!)
  })

  test('CoI 编码：点击 TE/EX/IN/RE 标签', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    const firstItem = page.locator('.coi-item').first()

    await firstItem.locator('.coi-code-btns button', { hasText: 'TE' }).click()
    await expect(firstItem.locator('.coi-code-btns button', { hasText: 'TE' })).toHaveClass(/el-button--primary/)

    await firstItem.locator('.coi-code-btns button', { hasText: 'EX' }).click()
    await expect(firstItem.locator('.coi-code-btns button', { hasText: 'EX' })).toHaveClass(/el-button--primary/)

    // 再点同一个取消
    await firstItem.locator('.coi-code-btns button', { hasText: 'EX' }).click()
    await expect(firstItem.locator('.coi-code-btns button', { hasText: 'EX' })).not.toHaveClass(/el-button--primary/)
  })

  test('已编码统计数字正确', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await page.locator('.coi-item').nth(0).locator('.coi-code-btns button', { hasText: 'TE' }).click()
    await page.locator('.coi-item').nth(1).locator('.coi-code-btns button', { hasText: 'IN' }).click()

    await expect(page.locator('.coi-stats')).toContainText('已编码')
    await expect(page.locator('.coi-stats span').filter({ hasText: /已编码/ })).toContainText('2')
    await expect(page.locator('.coi-stats span').filter({ hasText: /未编码/ })).toContainText('1')
  })

  test('合并：选中 2 条后合并，列表减少 1 条', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await page.locator('.coi-item').nth(0).locator('.el-checkbox').click()
    await page.locator('.coi-item').nth(1).locator('.el-checkbox').click()
    await expect(page.locator('.coi-actions button', { hasText: /合并选中/ })).toContainText('2')

    await page.locator('.coi-actions button', { hasText: /合并选中/ }).click()
    await page.locator('.el-message-box__btns .el-button--primary').click()
    await expect(page.getByText('合并成功')).toBeVisible()
    await expect(page.locator('.coi-item')).toHaveCount(2)
  })

  test('合并：选中不足 2 条时按钮禁用', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await expect(page.locator('.coi-actions button', { hasText: /合并选中/ })).toBeDisabled()

    await page.locator('.coi-item').nth(0).locator('.el-checkbox').click()
    await expect(page.locator('.coi-actions button', { hasText: /合并选中/ })).toBeDisabled()
  })

  test('全选 / 取消全选', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await page.locator('.coi-actions .el-checkbox').click()
    await expect(page.locator('.coi-actions button', { hasText: /合并选中 \(3\)/ })).toBeVisible()

    await page.locator('.coi-actions .el-checkbox').click()
    await expect(page.locator('.coi-actions button', { hasText: /合并选中 \(0\)/ })).toBeVisible()
  })

  test('拆分：打开对话框并验证预览', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await page.locator('.coi-item').first().getByRole('button', { name: '拆分' }).click()
    await expect(page.getByRole('dialog', { name: '拆分发言' })).toBeVisible()
    await expect(page.getByText('在下方文本中点击选择拆分位置')).toBeVisible()

    // 用 JS 模拟光标位置后触发事件
    await page.evaluate(() => {
      const ta = document.querySelector('.split-textarea') as HTMLTextAreaElement
      if (ta) {
        ta.selectionStart = 10
        ta.selectionEnd = 10
        ta.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      }
    })
    await page.waitForTimeout(300)

    // 确认拆分按钮存在
    await expect(page.getByRole('button', { name: '确认拆分' })).toBeVisible()

    // 关闭
    await page.getByRole('button', { name: '取消' }).click()
    await expect(page.getByRole('dialog', { name: '拆分发言' })).not.toBeVisible()
  })

  test('删除单条发言', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await page.locator('.coi-item').last().getByRole('button', { name: '删除' }).click()
    await page.locator('.el-message-box__btns .el-button--primary').click()
    await expect(page.getByText('已删除')).toBeVisible()
    await expect(page.locator('.coi-item')).toHaveCount(2)
  })

  test('上移/下移调整顺序', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    const secondContent = await page.locator('.coi-item').nth(1).locator('.coi-content').textContent()
    await page.locator('.coi-item').nth(1).getByRole('button', { name: '↑' }).click()
    await page.waitForTimeout(600)

    const firstContent = await page.locator('.coi-item').first().locator('.coi-content').textContent()
    expect(firstContent?.trim()).toBe(secondContent?.trim())
  })

  test('第一条↑禁用，最后一条↓禁用', async ({ page }) => {
    const { groupName, sessionTitle } = await seedSession()
    await loginAsAdmin(page)
    await page.goto('/admin/coi-utterances')
    await selectGroupAndSession(page, groupName, sessionTitle)
    await page.getByRole('button', { name: '从转写导入' }).click()
    await expect(page.locator('.coi-item')).toHaveCount(3)

    await expect(page.locator('.coi-item').first().getByRole('button', { name: '↑' })).toBeDisabled()
    await expect(page.locator('.coi-item').last().getByRole('button', { name: '↓' })).toBeDisabled()
  })
})
