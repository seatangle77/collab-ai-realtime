import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { goToAdminPage, loginAsAdmin } from './admin-helpers'

function pageResponse<T>(items: T[], page = 1, pageSize = 20) {
  return { items, meta: { total: items.length, page, page_size: pageSize } }
}

function formInput(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('input').first()
}

test.describe.serial('Admin 窗口论证批量日志页', () => {
  test('支持基础加载、JSON 查看、过滤、导出、单删和批删', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')
    const table = page.locator('.el-table').first()

    let items = [
      {
        id: 'wmbr-1',
        session_id: 'sess-batch-1',
        window_start: '2026-04-10T10:00:00Z',
        members: [
          {
            user_id: 'user-1',
            reasoning_status: true,
            evidence_status: false,
            reasoning_source: '说明了原因。',
            evidence_source: '没有举例。',
          },
          {
            user_id: 'user-2',
            reasoning_status: false,
            evidence_status: true,
            reasoning_source: '只有结论。',
            evidence_source: '引用了案例。',
          },
        ],
        created_at: '2026-04-10T10:02:00Z',
      },
      {
        id: 'wmbr-2',
        session_id: 'sess-batch-2',
        window_start: '2026-04-10T11:00:00Z',
        members: [],
        created_at: '2026-04-10T11:02:00Z',
      },
      {
        id: 'wmbr-3',
        session_id: 'sess-batch-3',
        window_start: '2026-04-10T12:00:00Z',
        members: [
          {
            user_id: 'user-3',
            reasoning_status: null,
            evidence_status: null,
            reasoning_source: null,
            evidence_source: null,
          },
        ],
        created_at: '2026-04-10T12:02:00Z',
      },
    ]

    let mode: 'ok' | 'error' = 'ok'

    await loginAsAdmin(page)
    await page.route('**/api/admin/window-metrics-batch-reasoning/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()

      if (method === 'GET') {
        if (mode === 'error') {
          await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }) })
          return
        }

        const query = new URL(url).searchParams
        let filtered = [...items]
        if (query.get('session_id')) filtered = filtered.filter((item) => item.session_id === query.get('session_id'))
        if (query.get('window_start_from')) filtered = filtered.filter((item) => item.window_start >= query.get('window_start_from')!)
        if (query.get('window_start_to')) filtered = filtered.filter((item) => item.window_start <= query.get('window_start_to')!)
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

    await goToAdminPage(page, '/admin/window-metrics-batch-reasoning', '窗口论证批量日志')
    await expect(table.getByText('sess-batch-1')).toBeVisible()
    await expect(table.getByText('sess-batch-2')).toBeVisible()
    await expect(table.getByText('2', { exact: true })).toBeVisible()
    await expect(table.getByText('0', { exact: true })).toBeVisible()

    await table.getByRole('button', { name: '查看 JSON' }).first().click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText('reasoning_status')).toBeVisible()
    await expect(page.getByText('evidence_status')).toBeVisible()
    await expect(page.getByText('reasoning_source')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)

    await formInput(page, '会话 ID').fill('sess-batch-2')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('sess-batch-2')).toBeVisible()
    await expect(table.getByText('sess-batch-1')).toHaveCount(0)

    await page.getByRole('button', { name: '重置' }).click()
    await expect(table.getByText('sess-batch-1')).toBeVisible()

    const exportBtn = page.getByRole('button', { name: '导出选中' })
    await expect(exportBtn).toBeDisabled()

    const checkboxes = page.locator('.el-table__body .el-checkbox')
    await checkboxes.nth(0).click()
    await expect(exportBtn).toBeEnabled()

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      exportBtn.click(),
    ])
    const csvText = fs.readFileSync((await download.path()) as string, 'utf-8')
    expect(csvText).toContain('会话 ID')
    expect(csvText).toContain('成员数')
    expect(csvText).toContain('成员 JSON')
    expect(csvText).toContain('reasoning_status')

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.locator('.el-table').getByRole('button', { name: '删除' }).first().click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await expect(table.getByText('sess-batch-1')).toHaveCount(0)

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
    await expect(table.getByText('sess-batch-2')).toHaveCount(0)

    await table.getByRole('button', { name: '查看 JSON' }).first().click()
    await expect(page.getByText('null')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)

    mode = 'error'
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByText('{"detail":"boom"}')).toBeVisible()

    mode = 'ok'
    items = []
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByText('{"detail":"boom"}')).toHaveCount(0)
    await expect(page.locator('.el-table__body tbody tr')).toHaveCount(0)
  })
})
