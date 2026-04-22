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

test.describe.serial('Admin AI 推送分析页', () => {
  test('支持列表加载、筛选、单删、批删、导出和重置', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')
    const table = page.locator('.el-table').first()

    let items = [
      {
        id: 'apa-1',
        session_id: 'sess-ai-1',
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        state_type: 'stagnation',
        window_start: '2026-04-10T10:00:00Z',
        ai_needs_prompt: true,
        ai_anchor: {
          transcript_id: 't-1',
          speaker_id: 'sp-1',
          speaker_name: '成员甲',
          text: '我对这个功能还不是很理解',
        },
        ai_content: '你可以先说说自己的理解。',
        drop_reason: 'passed',
        created_at: '2026-04-10T10:02:00Z',
      },
      {
        id: 'apa-2',
        session_id: 'sess-ai-2',
        target_user_id: 'user-2',
        target_user_name: '用户乙',
        state_type: 'group_silence',
        window_start: '2026-04-10T11:00:00Z',
        ai_needs_prompt: true,
        ai_anchor: null,
        ai_content: '请大家分别说一下当前最关心的问题。',
        drop_reason: 'persist_failed',
        created_at: '2026-04-10T11:02:00Z',
      },
      {
        id: 'apa-3',
        session_id: 'sess-ai-3',
        target_user_id: 'user-3',
        target_user_name: null,
        state_type: 'shallow',
        window_start: '2026-04-10T12:00:00Z',
        ai_needs_prompt: false,
        ai_anchor: null,
        ai_content: null,
        drop_reason: 'needs_prompt_false',
        created_at: '2026-04-10T12:02:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/ai-push-analysis/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let filtered = [...items]
        if (query.get('session_id')) filtered = filtered.filter((item) => item.session_id === query.get('session_id'))
        if (query.get('target_user_id')) filtered = filtered.filter((item) => item.target_user_id === query.get('target_user_id'))
        if (query.get('state_type')) filtered = filtered.filter((item) => item.state_type === query.get('state_type'))
        if (query.get('ai_needs_prompt')) filtered = filtered.filter((item) => String(item.ai_needs_prompt) === query.get('ai_needs_prompt'))
        if (query.get('drop_reason')) filtered = filtered.filter((item) => item.drop_reason === query.get('drop_reason'))
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

    await goToAdminPage(page, '/admin/ai-push-analysis', 'AI 推送分析')
    await expect(table.getByText('用户甲')).toBeVisible()
    await expect(table.getByText('用户乙')).toBeVisible()
    await expect(table.getByText('落库失败')).toBeVisible()
    await expect(table.getByText('成员甲：我对这个功能还不是很理解')).toBeVisible()

    await formInput(page, '会话 ID').fill('sess-ai-2')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('用户乙')).toBeVisible()
    await expect(table.getByText('用户甲')).toHaveCount(0)

    await page.getByRole('button', { name: '重置' }).click()
    await formSelect(page, '触发类型').click()
    await page.getByRole('option', { name: 'group_silence' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('用户乙')).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await formSelect(page, '结果').click()
    await page.getByRole('option', { name: '落库失败' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await expect(table.getByText('用户乙')).toBeVisible()
    await expect(table.getByText('请大家分别说一下当前最关心的问题。')).toBeVisible()

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
    expect(csvText).toContain('目标用户')
    expect(csvText).toContain('结果')
    expect(csvText).toContain('用户甲')
    expect(csvText).toContain('用户乙')
    expect(csvText).not.toContain('sess-ai-3')

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.locator('.el-table').getByRole('button', { name: '删除' }).first().click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await expect(table.getByText('用户甲')).toHaveCount(0)

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
    await expect(table.getByText('用户乙')).toHaveCount(0)

    await page.getByRole('button', { name: '重置' }).click()
    await expect(table.getByText('不需要', { exact: true })).toBeVisible()
    await expect(table.getByText('—', { exact: true }).first()).toBeVisible()
  })

  test('接口失败时显示错误提示，空列表时页面不崩', async ({ page }) => {
    let mode: 'error' | 'empty' = 'error'

    await loginAsAdmin(page)
    await page.route('**/api/admin/ai-push-analysis/**', async (route) => {
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

    await goToAdminPage(page, '/admin/ai-push-analysis', 'AI 推送分析')
    await expect(page.getByText('{"detail":"boom"}')).toBeVisible()

    mode = 'empty'
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByText('{"detail":"boom"}')).toHaveCount(0)
    await expect(page.locator('.el-table__body tbody tr')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '导出选中' })).toBeDisabled()
  })
})
