import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { loginAsAdmin, goToAdminPage } from './admin-helpers'

function pageResponse<T>(items: T[], page = 1, pageSize = 20) {
  return { items, meta: { total: items.length, page, page_size: pageSize } }
}

function formInput(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('input').first()
}

function formSelect(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('.el-select').first()
}

test.describe.serial('Admin 关键词召回分析页', () => {
  test('支持列表加载、筛选、单删、批删、导出和重置', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')
    const table = page.locator('.el-table').first()

    let items = [
      {
        id: 'kra-1',
        session_id: 'sess-kra-1',
        window_start: '2026-04-10T10:00:00Z',
        keyword: '机器学习',
        needs_prompt: true,
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        llm_reason: '用户明确表示不理解这个概念。',
        created_at: '2026-04-10T10:02:00Z',
      },
      {
        id: 'kra-2',
        session_id: 'sess-kra-2',
        window_start: '2026-04-10T11:00:00Z',
        keyword: 'MVP 方案',
        needs_prompt: false,
        target_user_id: null,
        target_user_name: null,
        llm_reason: null,
        created_at: '2026-04-10T11:02:00Z',
      },
      {
        id: 'kra-3',
        session_id: 'sess-kra-3',
        window_start: '2026-04-10T12:00:00Z',
        keyword: '关键词_特殊%字符',
        needs_prompt: true,
        target_user_id: 'user-3',
        target_user_name: '用户丙',
        llm_reason: '对特殊关键词的解释不足。',
        created_at: '2026-04-10T12:02:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/info-gap-recall-analysis/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let filtered = [...items]
        if (query.get('session_id')) filtered = filtered.filter((item) => item.session_id === query.get('session_id'))
        if (query.get('keyword')) filtered = filtered.filter((item) => item.keyword.includes(query.get('keyword') as string))
        if (query.get('needs_prompt')) filtered = filtered.filter((item) => String(item.needs_prompt) === query.get('needs_prompt'))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(filtered)) })
        return
      }
      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        items = items.filter((item) => item.id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (method === 'POST' && url.includes('/batch-delete')) {
        const payload = route.request().postDataJSON() as { ids: string[] }
        items = items.filter((item) => !payload.ids.includes(item.id))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deleted: payload.ids.length }) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/info-gap-recall-analysis', '关键词召回分析')
    await expect(table.getByText('机器学习')).toBeVisible()
    await expect(table.getByText('MVP 方案')).toBeVisible()
    await expect(table.getByText('关键词_特殊%字符')).toBeVisible()
    await expect(table.getByText('—', { exact: true }).first()).toBeVisible()

    await formInput(page, '会话 ID').fill('sess-kra-2')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('MVP 方案')).toBeVisible()
    await expect(table.getByText('机器学习')).toHaveCount(0)

    await page.getByRole('button', { name: '重置' }).click()
    await formInput(page, '关键词').fill('特殊%字符')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('关键词_特殊%字符')).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await formSelect(page, 'LLM 判断推送').click()
    await page.getByRole('option', { name: '不需要' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('MVP 方案')).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    const exportBtn = page.getByRole('button', { name: '导出选中' })
    await expect(exportBtn).toBeDisabled()

    const checkboxes = page.locator('.el-table__body .el-checkbox')
    await checkboxes.nth(0).click()
    await checkboxes.nth(1).click()
    await expect(exportBtn).toBeEnabled()
    await expect(exportBtn).toHaveText(/导出选中\s*[（(]2[）)]/)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      exportBtn.click(),
    ])
    const csvText = fs.readFileSync((await download.path()) as string, 'utf-8')
    expect(csvText).toContain('会话 ID')
    expect(csvText).toContain('关键词')
    expect(csvText).toContain('LLM 理由')
    expect(csvText).toContain('机器学习')
    expect(csvText).toContain('MVP 方案')
    expect(csvText).not.toContain('关键词_特殊%字符')

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.locator('.el-table').getByRole('button', { name: '删除' }).first().click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await expect(table.getByText('机器学习')).toHaveCount(0)

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
    await expect(table.getByText('MVP 方案')).toHaveCount(0)

    await page.getByRole('button', { name: '重置' }).click()
    await expect(table.getByText('关键词_特殊%字符')).toBeVisible()
  })

  test('接口失败时显示错误提示，空列表时页面不崩', async ({ page }) => {
    let mode: 'error' | 'empty' = 'error'

    await loginAsAdmin(page)
    await page.route('**/api/admin/info-gap-recall-analysis/**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback()
        return
      }
      if (mode === 'error') {
        await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse([])) })
    })

    await goToAdminPage(page, '/admin/info-gap-recall-analysis', '关键词召回分析')
    await expect(page.getByText('{"detail":"boom"}')).toBeVisible()

    mode = 'empty'
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByText('{"detail":"boom"}')).toHaveCount(0)
    await expect(page.locator('.el-table__body tbody tr')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '导出选中' })).toBeDisabled()
  })
})
