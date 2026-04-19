import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { loginAsAdmin, goToAdminPage, toTruncatedText } from './admin-helpers'

type SpeechTranscript = {
  transcript_id: string
  group_id: string
  session_id: string
  user_id: string | null
  speaker: string | null
  text: string | null
  start: string | null
  end: string | null
  duration: number | null
  created_at: string | null
  audio_url: string | null
  confidence: number | null
  speaker_confidence: number | null
  speaker_user_id: string | null
  original_text: string | null
  is_edited: boolean
}

function pageResponse<T>(items: T[], page = 1, pageSize = 20) {
  return { items, meta: { total: items.length, page, page_size: pageSize } }
}

function formInput(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('input').first()
}

test.describe.serial('Admin 语音转写页面', () => {
  test('1. 支持筛选、截断+查看全文、单删和批删', async ({ page }) => {
    const longText = '这是一段超长转写文本，用于验证截断和查看全文。'.repeat(12)
    let transcripts: SpeechTranscript[] = [
      {
        transcript_id: 'tr-1',
        group_id: 'group-a',
        session_id: 'session-a',
        user_id: 'u-1',
        speaker: '张三',
        text: longText,
        start: '2026-04-14T10:00:00Z',
        end: '2026-04-14T10:00:12Z',
        duration: 12.34,
        created_at: '2026-04-14T10:00:12Z',
        audio_url: null,
        confidence: 0.923,
        speaker_confidence: 0.811,
        speaker_user_id: 'u-1',
        original_text: null,
        is_edited: false,
      },
      {
        transcript_id: 'tr-2',
        group_id: 'group-b',
        session_id: 'session-b',
        user_id: null,
        speaker: '李四',
        text: '短文本',
        start: '2026-04-14T10:01:00Z',
        end: '2026-04-14T10:01:03Z',
        duration: 3.0,
        created_at: '2026-04-14T10:01:03Z',
        audio_url: null,
        confidence: 0.777,
        speaker_confidence: null,
        speaker_user_id: null,
        original_text: null,
        is_edited: true,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/speech-transcripts/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        const query = new URL(url).searchParams
        let items = [...transcripts]
        if (query.get('session_id')) items = items.filter((i) => i.session_id === query.get('session_id'))
        if (query.get('group_id')) items = items.filter((i) => i.group_id === query.get('group_id'))
        if (query.get('speaker')) items = items.filter((i) => (i.speaker || '').includes(query.get('speaker')!))
        if (query.get('text')) items = items.filter((i) => (i.text || '').includes(query.get('text')!))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(items)) })
        return
      }
      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        transcripts = transcripts.filter((item) => item.transcript_id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (method === 'POST' && url.includes('/batch-delete')) {
        const payload = route.request().postDataJSON() as { ids: string[] }
        transcripts = transcripts.filter((item) => !payload.ids.includes(item.transcript_id))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deleted: payload.ids.length }) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/speech-transcripts', '语音转写')
    await expect(page.getByText(toTruncatedText(longText, 80))).toBeVisible()

    const row = page.getByRole('row').filter({ hasText: '张三' }).first()
    await row.getByRole('button', { name: '查看全文' }).click()
    const dialog = page.getByRole('dialog', { name: /张三 - 转写文本/ })
    await expect(dialog.locator('textarea')).toHaveValue(longText)
    await page.keyboard.press('Escape')

    await formInput(page, '说话人').fill('张')
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: '张三' })).toBeVisible()

    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('删除成功')).toBeVisible()

    await page.getByRole('button', { name: '重置' }).click()
    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('成功删除 1 条记录')).toBeVisible()
  })

  test('2. 异常、边界、极端输入可稳定处理', async ({ page }) => {
    const edgeText = '边界文本_%_[]()<>'.repeat(300)
    let firstLoad = true
    let transcripts: SpeechTranscript[] = [
      {
        transcript_id: 'tr-edge-1',
        group_id: 'group-edge',
        session_id: 'session-edge',
        user_id: null,
        speaker: null,
        text: edgeText,
        start: null,
        end: null,
        duration: null,
        created_at: null,
        audio_url: null,
        confidence: null,
        speaker_confidence: null,
        speaker_user_id: null,
        original_text: null,
        is_edited: false,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/speech-transcripts/**', async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (method === 'GET') {
        if (firstLoad) {
          firstLoad = false
          await route.fulfill({ status: 500, contentType: 'text/plain', body: '加载失败（mock 500）' })
          return
        }
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(transcripts)) })
        return
      }
      if (method === 'DELETE') {
        const id = new URL(url).pathname.split('/').pop() as string
        if (id === 'tr-edge-1') {
          await route.fulfill({ status: 404, contentType: 'text/plain', body: '转写记录不存在' })
          return
        }
        transcripts = transcripts.filter((item) => item.transcript_id !== id)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (method === 'POST' && url.includes('/batch-delete')) {
        await route.fulfill({ status: 422, contentType: 'text/plain', body: 'ids 不能为空' })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/speech-transcripts', '语音转写')
    await expect(page.getByText('加载失败（mock 500）')).toBeVisible()

    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByText(toTruncatedText(edgeText, 80))).toBeVisible()

    const edgeRow = page.getByRole('row').filter({ hasText: 'group-edge' }).first()
    await edgeRow.getByRole('button', { name: '查看全文' }).click()
    await expect(page.getByRole('dialog').locator('textarea')).toHaveValue(edgeText)
    await page.keyboard.press('Escape')

    await edgeRow.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('转写记录不存在')).toBeVisible()

    await page.locator('.el-table__body .el-checkbox').first().click()
    await page.getByRole('button', { name: /批量删除/ }).click()
    await page.getByRole('button', { name: '删除' }).last().click()
    await expect(page.getByText('ids 不能为空')).toBeVisible()
  })

  test('3. 导出选中 - 未选时按钮禁用', async ({ page }) => {
    await loginAsAdmin(page)
    await page.route('**/api/admin/speech-transcripts/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse([])) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/speech-transcripts', '语音转写')
    await expect(page.getByRole('button', { name: '导出选中' })).toBeDisabled()
  })

  test('4. 导出选中 - 选中两条转写导出 CSV 且包含完整文本', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定，这里主测 Chromium/Firefox')

    const longText1 = '第一段完整转写文本-'.repeat(8)
    const longText2 = '第二段完整转写文本-'.repeat(6)
    const longText3 = '第三段不应被导出的文本-'.repeat(6)
    const transcripts: SpeechTranscript[] = [
      {
        transcript_id: 'tr-export-1',
        group_id: 'group-export',
        session_id: 'session-export',
        user_id: 'u-export-1',
        speaker: '导出甲',
        text: longText1,
        start: '2026-04-14T10:00:00Z',
        end: '2026-04-14T10:00:12Z',
        duration: 12.34,
        created_at: '2026-04-14T10:00:12Z',
        audio_url: null,
        confidence: 0.923,
        speaker_confidence: 0.811,
        speaker_user_id: 'u-export-1',
        original_text: null,
        is_edited: false,
      },
      {
        transcript_id: 'tr-export-2',
        group_id: 'group-export',
        session_id: 'session-export',
        user_id: 'u-export-2',
        speaker: '导出乙',
        text: longText2,
        start: '2026-04-14T10:01:00Z',
        end: '2026-04-14T10:01:09Z',
        duration: 9.0,
        created_at: '2026-04-14T10:01:09Z',
        audio_url: null,
        confidence: 0.777,
        speaker_confidence: 0.701,
        speaker_user_id: 'u-export-2',
        original_text: null,
        is_edited: false,
      },
      {
        transcript_id: 'tr-export-3',
        group_id: 'group-export',
        session_id: 'session-export',
        user_id: 'u-export-3',
        speaker: '导出丙',
        text: longText3,
        start: '2026-04-14T10:02:00Z',
        end: '2026-04-14T10:02:05Z',
        duration: 5.0,
        created_at: '2026-04-14T10:02:05Z',
        audio_url: null,
        confidence: 0.666,
        speaker_confidence: 0.655,
        speaker_user_id: 'u-export-3',
        original_text: null,
        is_edited: false,
      },
    ]

    await loginAsAdmin(page)
    await page.route('**/api/admin/speech-transcripts/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageResponse(transcripts)) })
        return
      }
      await route.fallback()
    })

    await goToAdminPage(page, '/admin/speech-transcripts', '语音转写')

    const checkboxes = page.locator('.el-table__body .el-checkbox')
    await checkboxes.nth(0).click()
    await checkboxes.nth(1).click()

    const exportBtn = page.getByRole('button', { name: /导出选中/ })
    await expect(exportBtn).toBeEnabled()
    await expect(exportBtn).toHaveText(/导出选中\s*[（(]2[）)]/)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      exportBtn.click(),
    ])

    const downloadPath = await download.path()
    expect(downloadPath).not.toBeNull()
    const csvText = fs.readFileSync(downloadPath as string, 'utf-8')

    expect(csvText).toContain('转写 ID')
    expect(csvText).toContain('群组 ID')
    expect(csvText).toContain('会话 ID')
    expect(csvText).toContain('说话人')
    expect(csvText).toContain('转写文本')
    expect(csvText).toContain(longText1)
    expect(csvText).toContain(longText2)
    expect(csvText).not.toContain(longText3)
  })
})
