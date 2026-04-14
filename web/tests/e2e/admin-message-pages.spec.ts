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
        state_type: 'low_participation',
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
        state_type: 'low_participation',
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

})
