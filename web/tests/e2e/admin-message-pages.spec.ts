import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { loginAsAdmin, goToAdminPage, toTruncatedText, expectTextLooksFormattedDate } from './admin-helpers'

function pageResponse<T>(items: T[], page = 1, pageSize = 20) {
  return { items, meta: { total: items.length, page, page_size: pageSize } }
}

test.describe.serial('Admin 文本与消息类页面', () => {
  test('1. 推送日志页支持内容截断、全文弹窗、状态展示、时间格式化、单删和批删', async ({ page }) => {
    let logs = [
      {
        id: 'pl-1',
        session_id: 'session-log-1',
        session_title: '推送日志会话',
        state_id: 'state-1',
        state_type: 'stagnation',
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        push_content: '这是一条很长的推送日志内容，用来验证列表页的截断显示以及查看全文弹窗是否展示完整文本。',
        push_channel: 'web',
        jpush_message_id: 'jpush-1',
        delivery_status: 'failed',
        triggered_at: '2026-04-10T08:00:00Z',
        delivered_at: '2026-04-10T08:01:00Z',
      },
      {
        id: 'pl-2',
        session_id: 'session-log-2',
        session_title: '第二条推送日志',
        state_id: 'state-2',
        state_type: 'deadlock',
        target_user_id: 'user-2',
        target_user_name: '用户乙',
        push_content: '短内容',
        push_channel: 'app',
        jpush_message_id: 'jpush-2',
        delivery_status: 'delivered',
        triggered_at: '2026-04-10T09:00:00Z',
        delivered_at: '2026-04-10T09:01:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/push-logs/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(logs)) })
        return
      }
      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        logs = logs.filter((item) => item.id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (method === 'POST' && url.includes('/batch-delete')) {
        const payload = route.request().postDataJSON() as { ids: string[] }
        logs = logs.filter((item) => !payload.ids.includes(item.id))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deleted: payload.ids.length }) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/push-logs', '推送日志')
    await expect(page.getByText(toTruncatedText(logs[0].push_content, 40))).toBeVisible()
    const pushLogRow = page.getByRole('row').filter({ hasText: '推送日志会话' }).first()
    await pushLogRow.getByRole('button', { name: '查看全文' }).click()
    const pushLogDialog = page.getByRole('dialog', { name: /推送日志会话 - 推送内容/ })
    await expect(pushLogDialog.locator('textarea')).toHaveValue(logs[0].push_content)
    await page.keyboard.press('Escape')
    await expect(page.locator('.el-tag').filter({ hasText: '失败' })).toBeVisible()
    const deliveredAtText = (await pushLogRow.getByRole('cell').nth(8).innerText()).trim()
    await expectTextLooksFormattedDate(deliveredAtText)
    await pushLogRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('2. 推送队列页支持状态映射、pending 高亮、全文弹窗、时间格式化、单删和批删', async ({ page }) => {
    let queue = [
      {
        id: 'pq-1',
        session_id: 'session-queue-1',
        session_title: '推送队列会话',
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        state_type: 'stagnation',
        push_content: '这是一条等待发送的推送队列内容，用来验证查看全文弹窗。',
        analysis_window_start: '2026-04-10T10:00:00Z',
        status: 'pending',
        created_at: '2026-04-10T10:01:00Z',
        delivered_at: null,
      },
      {
        id: 'pq-2',
        session_id: 'session-queue-2',
        session_title: '已送达队列会话',
        target_user_id: 'user-2',
        target_user_name: '用户乙',
        state_type: 'deadlock',
        push_content: '已送达内容',
        analysis_window_start: '2026-04-10T11:00:00Z',
        status: 'delivered',
        created_at: '2026-04-10T11:01:00Z',
        delivered_at: '2026-04-10T11:02:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/push-queue/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(queue)) })
        return
      }
      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        queue = queue.filter((item) => item.id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (method === 'POST' && url.includes('/batch-delete')) {
        const payload = route.request().postDataJSON() as { ids: string[] }
        queue = queue.filter((item) => !payload.ids.includes(item.id))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deleted: payload.ids.length }) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/push-queue', '推送队列')
    await expect(page.locator('.el-tag').filter({ hasText: '待发送' })).toBeVisible()
    await expect(page.locator('.el-tag').filter({ hasText: '个人思路停滞' })).toBeVisible()
    const pushQueueRow = page.getByRole('row').filter({ hasText: '推送队列会话' }).first()
    await pushQueueRow.getByRole('button', { name: '查看全文' }).click()
    const pushQueueDialog = page.getByRole('dialog', { name: /推送队列会话 - 推送内容/ })
    await expect(pushQueueDialog.locator('textarea')).toHaveValue(queue[0].push_content)
    await page.keyboard.press('Escape')
    const analysisStartText = (await pushQueueRow.getByRole('cell').nth(6).innerText()).trim()
    await expectTextLooksFormattedDate(analysisStartText)
    await pushQueueRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('2.1 推送队列页导出选中：未选时禁用，选中两条后可导出 CSV', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const queue = [
      {
        id: 'pq-export-1',
        session_id: 'session-queue-export',
        session_title: '推送队列导出会话一',
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        state_type: 'stagnation',
        push_content: '第一条待发送推送内容，用来验证导出不会截断。'.repeat(4),
        analysis_window_start: '2026-04-10T10:00:00Z',
        status: 'pending',
        created_at: '2026-04-10T10:01:00Z',
        delivered_at: null,
      },
      {
        id: 'pq-export-2',
        session_id: 'session-queue-export',
        session_title: '推送队列导出会话二',
        target_user_id: 'user-2',
        target_user_name: '用户乙',
        state_type: 'deadlock',
        push_content: '第二条已送达推送内容，用来验证仅导出选中项。'.repeat(4),
        analysis_window_start: '2026-04-10T11:00:00Z',
        status: 'delivered',
        created_at: '2026-04-10T11:01:00Z',
        delivered_at: '2026-04-10T11:02:00Z',
      },
      {
        id: 'pq-export-3',
        session_id: 'session-queue-export',
        session_title: '推送队列导出会话三',
        target_user_id: 'user-3',
        target_user_name: '用户丙',
        state_type: 'topic_drift',
        push_content: '第三条内容不应导出。'.repeat(4),
        analysis_window_start: '2026-04-10T12:00:00Z',
        status: 'pending',
        created_at: '2026-04-10T12:01:00Z',
        delivered_at: null,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/push-queue/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(queue)) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/push-queue', '推送队列')

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

    expect(csvText).toContain('会话')
    expect(csvText).toContain('目标用户')
    expect(csvText).toContain('状态类型')
    expect(csvText).toContain('推送内容')
    expect(csvText).toContain('队列状态')
    expect(csvText).toContain('推送队列导出会话一')
    expect(csvText).toContain('推送队列导出会话二')
    expect(csvText).not.toContain('推送队列导出会话三')
    expect(csvText).toContain(queue[0].push_content)
  })

  test('2.2 推送队列页分页器支持 150 和 200 条/页', async ({ page }) => {
    const queue = [
      {
        id: 'pq-page-size-1',
        session_id: 'session-queue-page-size',
        session_title: '分页会话一',
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        state_type: 'stagnation',
        push_content: '分页内容一',
        analysis_window_start: '2026-04-10T10:00:00Z',
        status: 'pending',
        created_at: '2026-04-10T10:01:00Z',
        delivered_at: null,
      },
      {
        id: 'pq-page-size-2',
        session_id: 'session-queue-page-size',
        session_title: '分页会话二',
        target_user_id: 'user-2',
        target_user_name: '用户乙',
        state_type: 'deadlock',
        push_content: '分页内容二',
        analysis_window_start: '2026-04-10T11:00:00Z',
        status: 'delivered',
        created_at: '2026-04-10T11:01:00Z',
        delivered_at: '2026-04-10T11:02:00Z',
      },
    ]
    let lastRequestedPageSize = '20'

    await loginAsAdmin(page)
    await page.route('**/api/admin/push-queue/**', async (route) => {
      if (route.request().method() === 'GET') {
        const url = new URL(route.request().url())
        lastRequestedPageSize = url.searchParams.get('page_size') || '20'
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(pageResponse(queue, 1, Number(lastRequestedPageSize))),
        })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/push-queue', '推送队列')

    const sizeSelect = page.locator('.el-pagination .el-select').first()
    await expect(sizeSelect).toBeVisible()
    await sizeSelect.click()
    await expect(page.getByRole('option', { name: '150' })).toBeVisible()
    await expect(page.getByRole('option', { name: '200' })).toBeVisible()

    await page.getByRole('option', { name: '150' }).click()
    await expect.poll(() => lastRequestedPageSize).toBe('150')

    await sizeSelect.click()
    await page.getByRole('option', { name: '200' }).click()
    await expect.poll(() => lastRequestedPageSize).toBe('200')
  })

})
