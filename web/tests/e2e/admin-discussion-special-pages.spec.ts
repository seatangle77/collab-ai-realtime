import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { loginAsAdmin, goToAdminPage, toTruncatedText } from './admin-helpers'

function pageResponse<T>(items: T[], page = 1, pageSize = 20) {
  return {
    items,
    meta: {
      total: items.length,
      page,
      page_size: pageSize,
    },
  }
}

function formInput(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('input').first()
}

function formSelect(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('.el-select').first()
}

test.describe.serial('Admin 讨论摘要与讨论状态页面', () => {
  test('1. 讨论摘要页支持查询、截断展示、查看全文、编辑、单删和批删', async ({ page }) => {
    let summaries = [
      {
        id: 'ds-long',
        session_id: 'session-summary-1',
        session_title: '摘要测试会话',
        version: 1,
        content: '这是一段很长的讨论摘要内容，用来验证列表页只显示截断文本，而弹窗里能看到完整内容。这里继续补充更多文字，确保超过八十个字符。',
        window_start: '2026-04-10T08:00:00Z',
        window_end: '2026-04-10T08:10:00Z',
        created_at: '2026-04-10T08:11:00Z',
      },
      {
        id: 'ds-short',
        session_id: 'session-summary-2',
        session_title: '第二个摘要会话',
        version: 2,
        content: '简短摘要',
        window_start: '2026-04-10T09:00:00Z',
        window_end: '2026-04-10T09:10:00Z',
        created_at: '2026-04-10T09:11:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/discussion-summaries/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()

      if (method === 'GET' && url.includes('/api/admin/discussion-summaries/')) {
        if (/\/api\/admin\/discussion-summaries\/[^/?]+$/.test(new URL(url).pathname)) {
          const id = new URL(url).pathname.split('/').pop() as string
          const item = summaries.find((s) => s.id === id)
          await route.fulfill({ status: item ? 200 : 404, contentType: 'application/json', body: JSON.stringify(item ?? { detail: 'not found' }) })
          return
        }

        const query = new URL(url).searchParams
        let items = [...summaries]
        if (query.get('session_id')) items = items.filter((s) => s.session_id === query.get('session_id'))
        if (query.get('version')) items = items.filter((s) => s.version === Number(query.get('version')))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(items)) })
        return
      }

      if (method === 'PUT') {
        const id = new URL(url).pathname.split('/').pop() as string
        const payload = route.request().postDataJSON() as { content: string }
        summaries = summaries.map((s) => (s.id === id ? { ...s, content: payload.content } : s))
        const updated = summaries.find((s) => s.id === id)
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(updated) })
        return
      }

      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        summaries = summaries.filter((s) => s.id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }

      if (method === 'POST' && url.includes('/batch-delete')) {
        const payload = route.request().postDataJSON() as { ids: string[] }
        const deleted = payload.ids.length
        summaries = summaries.filter((s) => !payload.ids.includes(s.id))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deleted }) })
        return
      }

      await route.fallback()
    })

    await goToAdminPage(page, '/admin/discussion-summaries', '讨论摘要')

    await formInput(page, '会话 ID').fill('session-summary-1')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: '摘要测试会话' })).toBeVisible()

    const preview = toTruncatedText(summaries[0].content, 80)
    const summaryRow = page.getByRole('row').filter({ hasText: '摘要测试会话' }).first()
    const previewCellText = (await summaryRow.getByRole('cell').nth(6).innerText()).trim()
    expect(previewCellText).toBe(preview)

    await summaryRow.getByRole('button', { name: '查看' }).click()
    const viewDialog = page.getByRole('dialog', { name: /摘要测试会话 - v1/ })
    await expect(viewDialog.locator('textarea')).toHaveValue(summaries[0].content)
    await page.keyboard.press('Escape')

    await summaryRow.getByRole('button', { name: '编辑' }).click()
    const editDialog = page.getByRole('dialog', { name: /摘要测试会话 - 编辑摘要/ })
    await editDialog.locator('textarea').fill('编辑后的摘要内容')
    await editDialog.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('摘要更新成功')).toBeVisible()
    await expect(page.getByText('编辑后的摘要内容')).toBeVisible()

    await summaryRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('1.1 讨论摘要页导出选中：未选时禁用，选中两条后可导出 CSV', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const summaries = [
      {
        id: 'ds-export-1',
        session_id: 'session-summary-export',
        session_title: '导出摘要会话一',
        version: 1,
        content: '第一条完整摘要内容，用于验证导出不会截断。'.repeat(4),
        window_start: '2026-04-10T08:00:00Z',
        window_end: '2026-04-10T08:10:00Z',
        created_at: '2026-04-10T08:11:00Z',
      },
      {
        id: 'ds-export-2',
        session_id: 'session-summary-export',
        session_title: '导出摘要会话二',
        version: 2,
        content: '第二条完整摘要内容，用于验证导出只包含选中项。'.repeat(4),
        window_start: '2026-04-10T09:00:00Z',
        window_end: '2026-04-10T09:10:00Z',
        created_at: '2026-04-10T09:11:00Z',
      },
      {
        id: 'ds-export-3',
        session_id: 'session-summary-export',
        session_title: '导出摘要会话三',
        version: 3,
        content: '第三条摘要内容不应导出。'.repeat(4),
        window_start: '2026-04-10T10:00:00Z',
        window_end: '2026-04-10T10:10:00Z',
        created_at: '2026-04-10T10:11:00Z',
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/discussion-summaries/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(summaries)) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/discussion-summaries', '讨论摘要')

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

    expect(csvText).toContain('会话标题')
    expect(csvText).toContain('版本')
    expect(csvText).toContain('摘要内容')
    expect(csvText).toContain('导出摘要会话一')
    expect(csvText).toContain('导出摘要会话二')
    expect(csvText).not.toContain('导出摘要会话三')
    expect(csvText).toContain(summaries[0].content)
  })

  test('2. 讨论摘要页空内容保存被前端拦截', async ({ page }) => {
    const summaries = [
      {
        id: 'ds-only',
        session_id: 'session-summary-empty',
        session_title: '空内容摘要会话',
        version: 1,
        content: '原始内容',
        window_start: '2026-04-10T10:00:00Z',
        window_end: '2026-04-10T10:10:00Z',
        created_at: '2026-04-10T10:11:00Z',
      },
    ]

    let putCount = 0
    await loginAsAdmin(page)
    await page.route('**/api/admin/discussion-summaries/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(summaries)) })
        return
      }
      if (method === 'PUT') {
        putCount += 1
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(summaries[0]) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/discussion-summaries', '讨论摘要')
    await page.getByRole('button', { name: '编辑' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.locator('textarea').fill('   ')
    await dialog.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('摘要内容不能为空')).toBeVisible()
    expect(putCount).toBe(0)
  })

  test('3. 讨论状态页支持筛选、标签颜色、查看指标和空指标提示、单删与批删', async ({ page }) => {
    let states = [
      {
        id: 'state-1',
        session_id: 'session-state-1',
        triggered_at: '2026-04-10T11:00:00Z',
        state_type: 'stagnation',
        target_user_id: 'user-1',
        target_user_name: '用户甲',
        trigger_metrics: { speaking_ratio: 0.12, silence_s: 60 },
        ai_analysis_done: true,
        push_sent: false,
      },
      {
        id: 'state-2',
        session_id: 'session-state-2',
        triggered_at: '2026-04-10T12:00:00Z',
        state_type: 'deadlock',
        target_user_id: 'user-2',
        target_user_name: '用户乙',
        trigger_metrics: null,
        ai_analysis_done: false,
        push_sent: true,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/discussion-states/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let items = [...states]
        if (query.get('state_type')) items = items.filter((s) => s.state_type === query.get('state_type'))
        if (query.get('ai_analysis_done')) items = items.filter((s) => String(s.ai_analysis_done) === query.get('ai_analysis_done'))
        if (query.get('push_sent')) items = items.filter((s) => String(s.push_sent) === query.get('push_sent'))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(items)) })
        return
      }
      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        states = states.filter((s) => s.id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (method === 'POST' && url.includes('/batch-delete')) {
        const payload = route.request().postDataJSON() as { ids: string[] }
        states = states.filter((s) => !payload.ids.includes(s.id))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deleted: payload.ids.length }) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/discussion-states', '讨论状态')

    await formSelect(page, '状态类型').click()
    await page.getByRole('option', { name: '个人思路停滞' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const lowParticipationRow = page.getByRole('row').filter({ hasText: '个人思路停滞' }).first()
    await expect(lowParticipationRow).toBeVisible()
    await expect(page.locator('.el-tag').filter({ hasText: '个人思路停滞' })).toBeVisible()

    await lowParticipationRow.getByRole('button', { name: '查看指标' }).click()
    await expect(page.getByRole('dialog')).toContainText('"speaking_ratio": 0.12')
    await page.keyboard.press('Escape')

    await page.getByRole('button', { name: '重置' }).click()
    await formSelect(page, '状态类型').click()
    await page.getByRole('option', { name: '讨论僵局' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const deadlockRow = page.getByRole('row').filter({ hasText: '讨论僵局' }).first()
    await deadlockRow.getByRole('button', { name: '查看指标' }).click()
    await expect(page.getByRole('dialog')).toContainText('暂无指标数据')
    await page.keyboard.press('Escape')

    await deadlockRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })
})
