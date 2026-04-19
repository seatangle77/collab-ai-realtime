import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { loginAsAdmin, goToAdminPage, expectTextLooksFormattedDate } from './admin-helpers'

function pageResponse<T>(items: T[], page = 1, pageSize = 20) {
  return { items, meta: { total: items.length, page, page_size: pageSize } }
}

function formInput(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('input').first()
}

function formSelect(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('.el-select').first()
}

test.describe.serial('Admin 分析与指标页面', () => {
  test('1. 窗口指标页显示 arg_density，支持布尔筛选、单删和批删', async ({ page }) => {
    let items = [
      {
        id: 'wm-1',
        session_id: 'session-window-1',
        user_id: 'user-1',
        user_name: '用户甲',
        window_start: '2026-04-10T10:00:00Z',
        window_end: '2026-04-10T10:05:00Z',
        speaking_ratio: 0.11,
        silence_s: 20,
        ttr: 0.22,
        arg_density: 0.33,
        srep: 0.44,
        info_gain: 0.55,
        has_reasoning: true,
        has_evidence: false,
        created_at: '2026-04-10T10:06:00Z',
      },
      {
        id: 'wm-2',
        session_id: 'session-window-2',
        user_id: 'user-2',
        user_name: '用户乙',
        window_start: '2026-04-10T11:00:00Z',
        window_end: '2026-04-10T11:05:00Z',
        speaking_ratio: 0.21,
        silence_s: 25,
        ttr: 0.32,
        arg_density: 0.43,
        srep: 0.54,
        info_gain: 0.65,
        has_reasoning: false,
        has_evidence: true,
        created_at: '2026-04-10T11:06:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/window-metrics/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let filtered = [...items]
        if (query.get('has_reasoning')) filtered = filtered.filter((item) => String(item.has_reasoning) === query.get('has_reasoning'))
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

    await goToAdminPage(page, '/admin/window-metrics', '窗口指标')
    await expect(page.getByText('论点密度')).toBeVisible()
    await formSelect(page, '有推理').click()
    await page.getByRole('option', { name: '是' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const windowRow = page.getByRole('row').filter({ hasText: '用户甲' }).first()
    await expect(windowRow).toBeVisible()
    await windowRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('1.1 窗口指标页导出选中：未选时禁用，选中两条后可导出 CSV', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const items = [
      {
        id: 'wm-export-1',
        session_id: 'session-window-export',
        user_id: 'user-export-1',
        user_name: '导出用户甲',
        window_start: '2026-04-10T10:00:00Z',
        window_end: '2026-04-10T10:05:00Z',
        speaking_ratio: 0.11,
        silence_s: 20,
        ttr: 0.22,
        arg_density: 0.33,
        srep: 0.44,
        info_gain: 0.55,
        has_reasoning: true,
        has_evidence: false,
        created_at: '2026-04-10T10:06:00Z',
      },
      {
        id: 'wm-export-2',
        session_id: 'session-window-export',
        user_id: 'user-export-2',
        user_name: '导出用户乙',
        window_start: '2026-04-10T11:00:00Z',
        window_end: '2026-04-10T11:05:00Z',
        speaking_ratio: 0.21,
        silence_s: 25,
        ttr: 0.32,
        arg_density: 0.43,
        srep: 0.54,
        info_gain: 0.65,
        has_reasoning: false,
        has_evidence: true,
        created_at: '2026-04-10T11:06:00Z',
      },
      {
        id: 'wm-export-3',
        session_id: 'session-window-export',
        user_id: 'user-export-3',
        user_name: '导出用户丙',
        window_start: '2026-04-10T12:00:00Z',
        window_end: '2026-04-10T12:05:00Z',
        speaking_ratio: 0.31,
        silence_s: 15,
        ttr: 0.42,
        arg_density: 0.53,
        srep: 0.64,
        info_gain: 0.75,
        has_reasoning: true,
        has_evidence: true,
        created_at: '2026-04-10T12:06:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/window-metrics/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(items)) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/window-metrics', '窗口指标')

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
    expect(csvText).toContain('用户')
    expect(csvText).toContain('发言比例')
    expect(csvText).toContain('论点密度')
    expect(csvText).toContain('有推理')
    expect(csvText).toContain('导出用户甲')
    expect(csvText).toContain('导出用户乙')
    expect(csvText).not.toContain('导出用户丙')
  })

  test('2. 信息缺口按钮页支持三态 status、has_clicked 筛选、点击时间展示、单删和批删', async ({ page }) => {
    let items = [
      {
        id: 'igb-1',
        session_id: 'session-igb-1',
        user_id: 'user-1',
        user_name: '用户甲',
        keyword: '机器学习',
        skw_score: 0.2345,
        status: 'pending',
        window_start: '2026-04-10T12:00:00Z',
        created_at: '2026-04-10T12:01:00Z',
        clicked_at: null,
      },
      {
        id: 'igb-2',
        session_id: 'session-igb-2',
        user_id: 'user-2',
        user_name: '用户乙',
        keyword: '深度学习',
        skw_score: 0.5345,
        status: 'clicked',
        window_start: '2026-04-10T13:00:00Z',
        created_at: '2026-04-10T13:01:00Z',
        clicked_at: '2026-04-10T13:05:00Z',
      },
      {
        id: 'igb-3',
        session_id: 'session-igb-3',
        user_id: 'user-3',
        user_name: '用户丙',
        keyword: '提示词工程',
        skw_score: 0.7345,
        status: 'dismissed',
        window_start: '2026-04-10T14:00:00Z',
        created_at: '2026-04-10T14:01:00Z',
        clicked_at: null,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/info-gap-buttons/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let filtered = [...items]
        if (query.get('status')) filtered = filtered.filter((item) => item.status === query.get('status'))
        if (query.get('has_clicked')) filtered = filtered.filter((item) => String(Boolean(item.clicked_at)) === query.get('has_clicked'))
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

    await goToAdminPage(page, '/admin/info-gap-buttons', '信息缺口按钮')
    await formSelect(page, '状态').click()
    await page.getByRole('option', { name: '已忽略' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: '提示词工程' })).toBeVisible()
    await page.getByRole('button', { name: '重置' }).click()
    await formSelect(page, '是否已点击').click()
    await page.getByRole('option', { name: '是' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const infoGapRow = page.getByRole('row').filter({ hasText: '深度学习' }).first()
    await expect(infoGapRow).toBeVisible()
    const clickedAtText = (await infoGapRow.getByRole('cell').nth(7).innerText()).trim()
    await expectTextLooksFormattedDate(clickedAtText)
    await infoGapRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('2.1 信息缺口按钮页导出选中：未选时禁用，选中两条后可导出 CSV', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const items = [
      {
        id: 'igb-export-1',
        session_id: 'session-igb-export',
        user_id: 'user-export-1',
        user_name: '导出用户甲',
        keyword: '机器学习',
        skw_score: 0.2345,
        status: 'pending',
        window_start: '2026-04-10T12:00:00Z',
        created_at: '2026-04-10T12:01:00Z',
        clicked_at: null,
      },
      {
        id: 'igb-export-2',
        session_id: 'session-igb-export',
        user_id: 'user-export-2',
        user_name: '导出用户乙',
        keyword: '深度学习',
        skw_score: 0.5345,
        status: 'clicked',
        window_start: '2026-04-10T13:00:00Z',
        created_at: '2026-04-10T13:01:00Z',
        clicked_at: '2026-04-10T13:05:00Z',
      },
      {
        id: 'igb-export-3',
        session_id: 'session-igb-export',
        user_id: 'user-export-3',
        user_name: '导出用户丙',
        keyword: '提示词工程',
        skw_score: 0.7345,
        status: 'dismissed',
        window_start: '2026-04-10T14:00:00Z',
        created_at: '2026-04-10T14:01:00Z',
        clicked_at: null,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/info-gap-buttons/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(items)) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/info-gap-buttons', '信息缺口按钮')

    const exportBtn = page.getByRole('button', { name: '导出选中' })
    await expect(exportBtn).toBeDisabled()

    const checkboxes = page.locator('.el-table__body .el-checkbox')
    await checkboxes.nth(0).click()
    await checkboxes.nth(1).click()

    await expect(exportBtn).toBeEnabled()

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      exportBtn.click(),
    ])
    const csvText = fs.readFileSync((await download.path()) as string, 'utf-8')

    expect(csvText).toContain('关键词')
    expect(csvText).toContain('SKW 分数')
    expect(csvText).toContain('状态')
    expect(csvText).toContain('点击时间')
    expect(csvText).toContain('机器学习')
    expect(csvText).toContain('深度学习')
    expect(csvText).not.toContain('提示词工程')
  })

  test('4. 关键词 SKW 页支持四位精度、高分样式、区间筛选边界、单删和批删', async ({ page }) => {
    let items = [
      {
        id: 'ks-1',
        session_id: 'session-ks-1',
        window_start: '2026-04-10T15:00:00Z',
        keyword: '协作',
        user_a_id: 'user-a1',
        user_a_name: '用户甲',
        user_b_id: 'user-b1',
        user_b_name: '用户乙',
        skw_score: 0.8123,
        created_at: '2026-04-10T15:01:00Z',
      },
      {
        id: 'ks-2',
        session_id: 'session-ks-2',
        window_start: '2026-04-10T16:00:00Z',
        keyword: '沟通',
        user_a_id: 'user-a2',
        user_a_name: '用户丙',
        user_b_id: 'user-b2',
        user_b_name: '用户丁',
        skw_score: 0.4567,
        created_at: '2026-04-10T16:01:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/keyword-skw/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let filtered = [...items]
        if (query.get('skw_score_min')) filtered = filtered.filter((item) => item.skw_score >= Number(query.get('skw_score_min')))
        if (query.get('skw_score_max')) filtered = filtered.filter((item) => item.skw_score <= Number(query.get('skw_score_max')))
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

    await goToAdminPage(page, '/admin/keyword-skw', '关键词 SKW')
    await expect(page.getByText('0.8123')).toBeVisible()
    await expect(page.locator('.high-score')).toContainText('0.8123')
    await formInput(page, 'SKW 最小值').fill('0.9000')
    await formInput(page, 'SKW 最大值').fill('0.1000')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByText('SKW 最小值不能大于最大值')).toBeVisible()
    await formInput(page, 'SKW 最小值').fill('0.7000')
    await formInput(page, 'SKW 最大值').fill('0.9000')
    await page.getByRole('button', { name: '查询' }).click()
    const keywordRow = page.getByRole('row').filter({ hasText: '协作' }).first()
    await expect(keywordRow).toBeVisible()
    await keywordRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('4.1 关键词 SKW 页导出选中：未选时禁用，选中两条后可导出 CSV', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const items = [
      {
        id: 'ks-export-1',
        session_id: 'session-ks-export',
        window_start: '2026-04-10T15:00:00Z',
        keyword: '协作',
        user_a_id: 'user-a1',
        user_a_name: '用户甲',
        user_b_id: 'user-b1',
        user_b_name: '用户乙',
        skw_score: 0.8123,
        skw_status: 'computed',
        created_at: '2026-04-10T15:01:00Z',
      },
      {
        id: 'ks-export-2',
        session_id: 'session-ks-export',
        window_start: '2026-04-10T16:00:00Z',
        keyword: '沟通',
        user_a_id: 'user-a2',
        user_a_name: '用户丙',
        user_b_id: 'user-b2',
        user_b_name: '用户丁',
        skw_score: 0.4567,
        skw_status: 'single_mention',
        created_at: '2026-04-10T16:01:00Z',
      },
      {
        id: 'ks-export-3',
        session_id: 'session-ks-export',
        window_start: '2026-04-10T17:00:00Z',
        keyword: '反馈',
        user_a_id: 'user-a3',
        user_a_name: '用户戊',
        user_b_id: 'user-b3',
        user_b_name: '用户己',
        skw_score: 0.3567,
        skw_status: null,
        created_at: '2026-04-10T17:01:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/keyword-skw/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(items)) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/keyword-skw', '关键词 SKW')

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

    expect(csvText).toContain('关键词')
    expect(csvText).toContain('用户 A')
    expect(csvText).toContain('用户 B')
    expect(csvText).toContain('状态')
    expect(csvText).toContain('SKW 分数')
    expect(csvText).toContain('协作')
    expect(csvText).toContain('沟通')
    expect(csvText).not.toContain('反馈')
  })
})
