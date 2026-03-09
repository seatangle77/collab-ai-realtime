import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

async function registerUserForE2E() {
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

  return { email, password }
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
    await expect(page.getByRole('heading', { name: '我的群组' })).toBeVisible()
  })

  test('3. 错误密码登录失败并显示错误提示', async ({ page }) => {
    const { email } = await registerUserForE2E()

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill('WrongPass123')
    await page.getByRole('button', { name: '登录' }).click()

    // 不应跳转到受保护页面，仍停留在登录页
    await expect(page).toHaveURL(/\/app\/login/)
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

    // 再次访问受保护页面会被拦截到登录页
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

    // 密码过短
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

    await expect(page.getByText(/邮箱已被注册/)).toBeVisible()
    await expect(page).toHaveURL(/\/app\/register/)
  })

  test('8. 登录失败 - 未注册邮箱', async ({ page }) => {
    const email = `not-exist-${Date.now()}@example.com`

    await page.goto('/app/login')
    await page.getByLabel('邮箱').fill(email)
    await page.getByLabel('密码').fill('9999')
    await page.getByRole('button', { name: '登录' }).click()

    // 未注册邮箱不应登录成功，仍在登录页
    await expect(page).toHaveURL(/\/app\/login/)
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
})

