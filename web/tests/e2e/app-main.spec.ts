import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

async function registerUserForE2E() {
  const email = `app-main-e2e-${Date.now()}@example.com`
  const password = '1234'
  const name = 'App Main E2E User'

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

test.describe('App 登录后主界面与头部信息', () => {
  test('1. 登录后首页展示当前用户信息与当前群组', async ({ page }) => {
    const { email, password, name } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()

    // 停留在首页
    await expect(page).toHaveURL(/\/app\/?$/)

    // 头部展示当前用户信息和默认当前群组
    const header = page.locator('.app-header-right')
    await expect(header.getByText(name, { exact: true })).toBeVisible()
    await expect(header.getByText(email)).toBeVisible()
    await expect(header.getByText('当前群组：未选择')).toBeVisible()

    // 首页欢迎区展示欢迎语和邮箱
    await expect(page.getByText('欢迎回来')).toBeVisible()
    await expect(page.locator('.app-home-card').getByText(email)).toBeVisible()
  })

  test('2. 登录后导航到我的群组与我的会话，仍展示当前用户与当前群组', async ({ page }) => {
    const { email, password, name } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/app\/?$/)

    // 我的群组
    await page.goto('/app/groups')
    await expect(page.getByRole('heading', { name: '我的群组' })).toBeVisible()
    const header = page.locator('.app-header-right')
    await expect(header.getByText(name, { exact: true })).toBeVisible()
    await expect(header.getByText(email)).toBeVisible()
    await expect(header.getByText('当前群组：未选择')).toBeVisible()

    // 我的会话
    await page.goto('/app/sessions')
    await expect(page.getByRole('heading', { name: '我的会话' })).toBeVisible()
    const headerSessions = page.locator('.app-header-right')
    await expect(headerSessions.getByText(name, { exact: true })).toBeVisible()
    await expect(headerSessions.getByText(email)).toBeVisible()
    await expect(headerSessions.getByText('当前群组：未选择')).toBeVisible()
  })

  test('3. 存在当前群组时头部和页面展示该群组名称', async ({ page }) => {
    const { email, password, name } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/app\/?$/)

    // 在浏览器上下文中设置当前群组
    const groupName = 'E2E 测试群组-很长很长的名字'
    await page.evaluate((name) => {
      window.localStorage.setItem(
        'app_current_group',
        JSON.stringify({ id: 'g-e2e-main', name }),
      )
    }, groupName)

    // 刷新后头部与首页使用新的群组名称
    await page.reload()
    const header = page.locator('.app-header-right')
    await expect(header.getByText(name, { exact: true })).toBeVisible()
    await expect(header.getByText(groupName)).toBeVisible()
    await expect(header.getByText('当前群组：')).toBeVisible()

    // 在我的群组页面也应展示该群组名称
    await page.goto('/app/groups')
    await expect(page.getByRole('heading', { name: '我的群组' })).toBeVisible()
    await expect(page.locator('.app-groups').getByText(groupName)).toBeVisible()
  })

  test('4. 登录后如果 app_user 被清空，页面仍可访问且头部不展示用户信息', async ({ page }) => {
    const { email, password, name } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/app\/?$/)

    // 模拟某些场景下 localStorage 中 app_user 被外部清空
    await page.evaluate(() => {
      window.localStorage.removeItem('app_user')
    })

    await page.reload()
    await expect(page).toHaveURL(/\/app\/?$/)

    // 头部仍然有退出按钮（因为 token 还在），但不再展示具体用户 name/email
    const header = page.locator('.app-header-right')
    await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
    await expect(header.getByText(name).first()).toHaveCount(0)
    await expect(header.getByText(email).first()).toHaveCount(0)
  })

  test('5. app_user 为非法 JSON 时不应导致页面崩溃', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('app_access_token', 'dummy-token')
      window.localStorage.setItem('app_user', 'not-json')
    })

    await page.goto('/app')
    // 仍能进入首页并看到主内容，不抛异常
    await expect(page).toHaveURL(/\/app\/?$/)
    await expect(page.locator('.app-logo')).toBeVisible()
  })
})

