import { test, expect } from '@playwright/test'
const cue = (id: string) => ({ push_log_id: id, session_id: 's1', group_id: 'g1', group_name: '测试小组', condition: 'glasses', target_user_name: '甲', push_content: `提示${id}：绳子的用途`, received_at: '2026-09-08T00:00:01Z', coding: null,
  generation_analysis: id === 'a' ? '成员提出绳子有用，但还没有解释具体用途。' : null,
  generation_anchor: id === 'a' ? { speaker_name: '甲', text: '我觉得绳子有用。' } : null,
})
test('AI matches are temporary, isolated by cue, and do not select evidence', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('admin_api_key', 'mock'))
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  let calls = 0
  let writes = 0
  await page.route('**/api/admin/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/admin/')) return route.continue()
    if (route.request().method() !== 'GET' && !path.endsWith('/related-discussion')) writes++
    let body: unknown = {}
    if (path.endsWith('/related-discussion')) {
      expect(route.request().postDataJSON()).toEqual({ task_type: 'moon' })
      calls++
      await pending
      body = { push_log_id: 'a', interpretation: '追问绳子的具体用途和判断依据。', suggested_code: 'discussed_not_adopted', coding_reason: '后续讨论提到用途，但未见用于形成决定。', matches: [{ transcript_id: 't1', text: '可以拿绳子捆绑东西', reason: '提到绳子的用途' }], analyzed_count: 1, excluded_boundary_count: 0 }
    } else if (path.endsWith('/cue-uptake-coding/groups')) body = [{ group_id: 'g1', group_name: '测试小组', condition: 'glasses', event_count: 2 }]
    else if (path.endsWith('/context')) body = { session_id: 's1', group_name: '测试小组', members: [], cues: [cue('a'), cue('b')], transcripts: [{ transcript_id: 't1', source_transcript_ids: ['t1'], speaker_name: '甲', text: '可以拿绳子捆绑东西', start: '2026-09-08T00:00:03Z' }] }
    else if (path.endsWith('/events')) body = { items: [cue('a'), cue('b')], meta: { total: 2, page: 1, page_size: 30 } }
    else if (path.endsWith('/progress')) body = { total: 2, coded: 0, uncoded: 2, completion_rate: 0, by_code: {} }
    else if (path.includes('/chat-sessions')) body = { items: [{ id: 's1', session_title: '测试会话' }], meta: { total: 1 } }
    await route.fulfill({ json: body })
  })
  await page.goto('/admin/cue-uptake-coding')
  const basis = page.locator('.generation-basis')
  await expect(basis).not.toHaveAttribute('open', '')
  await basis.locator('summary').click()
  await expect(basis).toContainText('成员提出绳子有用，但还没有解释具体用途。')
  await expect(basis).toContainText('我觉得绳子有用。')
  await expect(page.getByRole('button', { name: 'AI 分析提示与讨论', exact: true })).toBeDisabled()
  await page.locator('.related-controls .el-select__wrapper').click()
  await page.getByRole('option', { name: '月球求生', exact: true }).click()
  await page.getByRole('button', { name: 'AI 分析提示与讨论', exact: true }).click()
  await expect(page.getByRole('button', { name: '正在分析' })).toBeDisabled()
  await page.locator('.event-card').nth(1).click()
  await expect(basis).not.toHaveAttribute('open', '')
  await basis.locator('summary').click()
  await expect(basis).toContainText('无生成依据')
  await expect(basis).not.toContainText('我觉得绳子有用。')
  finish()
  await expect(page.getByRole('button', { name: 'AI 分析提示与讨论', exact: true })).toBeVisible()
  await expect(page.locator('.timeline-entry--related')).toHaveCount(0)
  await page.locator('.event-card').first().click()
  await expect(page.getByText('找到 1 条相关讨论', { exact: true })).toBeVisible()
  await expect(page.locator('.timeline-entry--related')).toHaveCount(1)
  await expect(page.getByText('AI 相关', { exact: true })).toBeVisible()
  await expect(page.locator('.timeline-entry--evidence')).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'AI 提示分析' })).toContainText('追问绳子的具体用途和判断依据。')
  await expect(page.locator('.code-options label.is-checked')).toHaveCount(0)
  await page.getByRole('button', { name: '采用推荐编码' }).click()
  await expect(page.locator('.code-options label.is-checked')).toContainText('讨论未采纳')
  await expect(page.locator('.timeline-entry--evidence')).toHaveCount(0)
  await page.getByRole('button', { name: '下一条', exact: true }).click()
  await expect(page.locator('.related-controls')).toContainText('1 / 1')
  await page.locator('.related-controls .el-select__wrapper').click()
  await page.getByRole('option', { name: '海上求生', exact: true }).click()
  await expect(page.locator('.timeline-entry--related')).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'AI 提示分析' })).toHaveCount(0)
  await page.screenshot({ path: '/tmp/cue-related-page.png', fullPage: true })
  await page.reload()
  await expect(page.getByRole('button', { name: 'AI 分析提示与讨论', exact: true })).toBeVisible()
  await expect(page.locator('.timeline-entry--related')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'AI 分析提示与讨论', exact: true })).toBeEnabled()
  expect(calls).toBe(1)
  expect(writes).toBe(0)
})
