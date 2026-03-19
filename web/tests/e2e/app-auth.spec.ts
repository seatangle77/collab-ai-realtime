import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_TOKEN = process.env.ADMIN_API_KEY || 'TestAdminKey123'

// 通过 API 注册测试用户，返回 email / password / userId
async function registerUserForE2E(): Promise<{ email: string; password: string; userId: string }> {
  const name = `用户${Date.now()}`
  const email = `app-e2e-${Date.now()}@example.com`
  const password = '1234'

  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`注册测试用户失败: ${res.status} - ${text}`)
  }

  // 登录取 userId（register 只返回消息，login 返回 user 对象）
  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error('测试用户登录失败')
  const loginData = await loginRes.json()

  return { email, password, userId: loginData.user.id }
}

// 通过 admin API 标记用户需要改密
async function markPasswordReset(userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/users/${userId}/mark-password-reset`, {
    method: 'POST',
    headers: { 'X-Admin-Token': ADMIN_TOKEN },
  })
  if (!res.ok) throw new Error(`标记改密失败: ${res.status}`)
}

test.describe('App 用户注册与登录', () => {
  test('1. 新用户注册成功并跳转到登录页', async ({ page }) => {
    await page.goto('/app/register')

    const name = `用户${Date.now()}`
    const email = `app-e2e-${Date.now()}@example.com`
    const password = '1234'

    await page.getByLabel('昵称').fill(name)
    await page.getByLabel('邮箱').fill(email)
    await page.getByPlaceholder('4 位密码').fill(password)
    await page.getByPlaceholder('再次输入密码').fill(password)

    await page.getByRole('button', { name: '注册' }).click()

    await expect(page.getByText('注册成功')).toBeVisible()
    await expect(page).toHaveURL(/\/app\/login/)
  })

  test('2. 未登录访问受保护页面会被重定向到登录，登录后跳回原页面', async ({ page }) => {
    const { email, password } = await registerUserForE2E()

    await page.goto('/app/groups')
    await expect(page).toHaveURL(/\/app\/login/)

    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/groups/)
  })

  test('3. 错误密码登录失败并显示错误提示', async ({ page }) => {
    const { email } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill('9999')
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/login/)
    await expect(page.locator('.auth-error')).toBeVisible()
  })

  test('4. 登录成功后刷新页面仍保持在受保护页面', async ({ page }) => {
    const { email, password } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/?$/)
    await page.reload()
    await expect(page).toHaveURL(/\/app\/?$/)
  })

  test('5. 退出登录后再次访问受保护页面会被拦截', async ({ page }) => {
    const { email, password } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/?$/)
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page).toHaveURL(/\/app\/login/)

    await page.goto('/app/groups')
    await expect(page).toHaveURL(/\/app\/login/)
  })

  test('6. 注册表单校验 - 必填项与密码一致性', async ({ page }) => {
    await page.goto('/app/register')

    // 昵称为空
    await page.getByRole('button', { name: '注册' }).click()
    await expect(page.getByText('请输入昵称')).toBeVisible()

    // 邮箱为空
    await page.getByLabel('昵称').fill('校验用户')
    await page.getByRole('button', { name: '注册' }).click()
    await expect(page.getByText('请输入邮箱')).toBeVisible()

    // 密码不等于 4 位
    await page.getByLabel('邮箱').fill('validate@example.com')
    await page.getByPlaceholder('4 位密码').fill('123')
    await page.getByPlaceholder('再次输入密码').fill('123')
    await page.getByRole('button', { name: '注册' }).click()
    await expect(page.getByText('请输入 4 位密码')).toBeVisible()

    // 确认密码不一致
    await page.getByPlaceholder('4 位密码').fill('1234')
    await page.getByPlaceholder('再次输入密码').fill('5678')
    await page.getByRole('button', { name: '注册' }).click()
    await expect(page.getByText('两次输入的密码不一致')).toBeVisible()
  })

  test('7. 注册失败 - 重复邮箱', async ({ page }) => {
    const { email, password } = await registerUserForE2E()

    await page.goto('/app/register')
    await page.getByLabel('昵称').fill('重复用户')
    await page.getByLabel('邮箱').fill(email)
    await page.getByPlaceholder('4 位密码').fill(password)
    await page.getByPlaceholder('再次输入密码').fill(password)
    await page.getByRole('button', { name: '注册' }).click()

    await expect(page.locator('.auth-error')).toBeVisible()
    await expect(page).toHaveURL(/\/app\/register/)
  })

  test('8. 登录失败 - 未注册邮箱', async ({ page }) => {
    const email = `not-exist-${Date.now()}@example.com`

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill('9999')
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/login/)
    await expect(page.locator('.auth-error')).toBeVisible()
  })

  test('9. 已登录用户访问登录/注册页会被重定向到首页', async ({ page }) => {
    const { email, password } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/?$/)

    await page.goto('/app/login')
    await expect(page).toHaveURL(/\/app\/?$/)

    await page.goto('/app/register')
    await expect(page).toHaveURL(/\/app\/?$/)
  })

  test('10. 登录后 password_needs_reset=true 跳转到改密页', async ({ page }) => {
    const { email, password, userId } = await registerUserForE2E()
    await markPasswordReset(userId)

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/app\/change-password/)
  })
})

test.describe.serial('AppChangePassword · 修改密码页', () => {
  // 每个用例都需要一个已登录且需要改密的用户
  async function setupUserNeedingPasswordReset(page: import('@playwright/test').Page) {
    const { email, password, userId } = await registerUserForE2E()
    await markPasswordReset(userId)

    // 通过 UI 登录（会自动跳到改密页）
    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/app\/change-password/)

    return { email, password }
  }

  test('1. 旧密码为空 → 显示错误提示', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByRole('button', { name: '保存新密码' }).click()
    await expect(page.getByText('请输入旧密码')).toBeVisible()
  })

  test('2. 新密码不等于 4 位 → 显示错误提示', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByPlaceholder('当前 4 位密码').fill('1234')
    await page.getByPlaceholder('新的 4 位密码', { exact: true }).fill('123')
    await page.getByPlaceholder('再次输入新的 4 位密码').fill('123')
    await page.getByRole('button', { name: '保存新密码' }).click()

    await expect(page.getByText('新密码必须为 4 位')).toBeVisible()
  })

  test('3. 两次新密码不一致 → 显示错误提示', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByPlaceholder('当前 4 位密码').fill('1234')
    await page.getByPlaceholder('新的 4 位密码', { exact: true }).fill('5678')
    await page.getByPlaceholder('再次输入新的 4 位密码').fill('9999')
    await page.getByRole('button', { name: '保存新密码' }).click()

    await expect(page.getByText('两次输入的新密码不一致')).toBeVisible()
  })

  test('4. 旧密码错误 → 显示 API 错误提示', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByPlaceholder('当前 4 位密码').fill('0000')
    await page.getByPlaceholder('新的 4 位密码', { exact: true }).fill('5678')
    await page.getByPlaceholder('再次输入新的 4 位密码').fill('5678')
    await page.getByRole('button', { name: '保存新密码' }).click()

    await expect(page.locator('.auth-error')).toBeVisible()
  })

  test('5. 改密成功 → 显示成功提示 → 跳转 /app', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByPlaceholder('当前 4 位密码').fill('1234')
    await page.getByPlaceholder('新的 4 位密码', { exact: true }).fill('5678')
    await page.getByPlaceholder('再次输入新的 4 位密码').fill('5678')
    await page.getByRole('button', { name: '保存新密码' }).click()

    await expect(page.getByText('密码修改成功')).toBeVisible()
    await expect(page).toHaveURL(/\/app\/?$/, { timeout: 3000 })
  })

  test('6. 改密成功后 localStorage app_user.password_needs_reset = false', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByPlaceholder('当前 4 位密码').fill('1234')
    await page.getByPlaceholder('新的 4 位密码', { exact: true }).fill('5678')
    await page.getByPlaceholder('再次输入新的 4 位密码').fill('5678')
    await page.getByRole('button', { name: '保存新密码' }).click()

    await expect(page.getByText('密码修改成功')).toBeVisible()
    await expect(page).toHaveURL(/\/app\/?$/, { timeout: 5000 })

    const passwordNeedsReset = await page.evaluate(() => {
      const user = JSON.parse(localStorage.getItem('app_user') ?? 'null')
      return user?.password_needs_reset ?? null
    })
    expect(passwordNeedsReset).toBe(false)
  })

  test('7. 改密成功后访问 /app/change-password 不再被守卫拦截回改密页', async ({ page }) => {
    await setupUserNeedingPasswordReset(page)

    await page.getByPlaceholder('当前 4 位密码').fill('1234')
    await page.getByPlaceholder('新的 4 位密码', { exact: true }).fill('5678')
    await page.getByPlaceholder('再次输入新的 4 位密码').fill('5678')
    await page.getByRole('button', { name: '保存新密码' }).click()

    await expect(page.getByText('密码修改成功')).toBeVisible()
    await expect(page).toHaveURL(/\/app\/?$/, { timeout: 5000 })

    // 手动访问 change-password，应正常显示（不会被重定向回来）
    await page.goto('/app/change-password')
    await expect(page).toHaveURL(/\/app\/change-password/)
    await expect(page.getByRole('button', { name: '保存新密码' })).toBeVisible()
  })
})
