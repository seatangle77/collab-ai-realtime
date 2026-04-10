import { expect, type Page } from '@playwright/test'

export const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
export const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

export async function loginAsAdmin(page: Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await expect(page.getByRole('heading', { name: '用户管理' })).toBeVisible()
}

export async function goToAdminPage(page: Page, path: string, heading: string) {
  await page.goto(path)
  await expect(page).toHaveURL(new RegExp(path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  await expect(page.getByRole('heading', { name: heading })).toBeVisible()
}

export async function loginAsAdminAndGoToPage(page: Page, path: string, heading: string) {
  await loginAsAdmin(page)
  await goToAdminPage(page, path, heading)
}

export async function adminGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'X-Admin-Token': ADMIN_API_KEY },
  })
  if (!res.ok) {
    throw new Error(`admin GET ${path} failed: ${res.status} ${await res.text()}`)
  }
  return (await res.json()) as T
}

export async function adminPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`admin PUT ${path} failed: ${res.status} ${await res.text()}`)
  }
  return (await res.json()) as T
}

export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function toTruncatedText(fullText: string, maxLength: number): string {
  if (fullText.length <= maxLength) return fullText
  return `${fullText.slice(0, maxLength)}...`
}

export async function expectTextLooksFormattedDate(text: string) {
  expect(text).toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|-/)
  expect(text).not.toContain('T')
}
