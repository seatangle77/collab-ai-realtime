import { test, expect } from '@playwright/test'

test('组别筛选立即查询、重置分页，并保留到详情返回链接', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('admin_api_key', 'test-only'))
  await page.route('**/api/admin/groups/**', route => route.fulfill({ json: {
    items: [{ id: 'g1', name: 'G01', is_active: true }, { id: 'g2', name: 'G02', is_active: true }],
    meta: { page: 1, page_size: 200, total: 2 },
  } }))
  const requests: URL[] = []
  await page.route(/\/api\/admin\/voice-profiles(?:\?|$)/, route => {
    const url = new URL(route.request().url())
    requests.push(url)
    return route.fulfill({ json: {
      items: [{ id: 'v1', user_id: 'u1', user_name: '测试用户', primary_group_id: url.searchParams.get('group_id'), sample_count: 1, has_embedding: false, created_at: '2026-01-01T00:00:00Z' }],
      meta: { page: Number(url.searchParams.get('page')), page_size: 200, total: 201 },
    } })
  })
  await page.route('**/api/admin/voice-profiles/v1', route => route.fulfill({ json: {
    profile: { id: 'v1', user_id: 'u1', sample_audio_urls: [], created_at: '2026-01-01T00:00:00Z' },
  } }))
  await page.goto('/admin/voice-profiles?page=2&page_size=200')
  await expect.poll(() => requests.length).toBe(1)
  await page.locator('.el-form-item').filter({ has: page.getByRole('combobox', { name: '组别', exact: true }) }).locator('.el-select__wrapper').click()
  await page.getByRole('option', { name: 'G02（g2）', exact: true }).click()
  await expect.poll(() => requests.at(-1)?.searchParams.get('group_id')).toBe('g2')
  expect(requests.at(-1)?.searchParams.get('page')).toBe('1')
  expect(requests.at(-1)?.searchParams.get('page_size')).toBe('200')
  await page.getByRole('button', { name: '查看详情' }).first().click()
  await expect(page).toHaveURL(/group_id=g2/)
  await page.getByRole('button', { name: '返回列表' }).click()
  await expect(page.locator('.admin-voice-profiles-filters').getByText('G02（g2）', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重置', exact: true }).click()
  await expect.poll(() => requests.at(-1)?.searchParams.has('group_id')).toBe(false)
})
