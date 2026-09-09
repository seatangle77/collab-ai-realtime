import { test, expect } from '@playwright/test'

test('saved final version excludes internal noise after reload and preserves outside originals', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('admin_api_key', 'mock'))
  const group = {group_id:'g', group_name:'测试小组', condition:'glasses', transcript_count:4, corrected_count:1}
  const session = {...group, session_id:'s', session_title:'测试会话', created_at:'2026-09-08T00:00:00Z', started_at:'2026-09-08T00:00:00Z'}
  const rows = ['前面的原文', '完整录音正文', '中间胡乱识别不能进入正文', '后面的原文'].map((text, i) => ({
    transcript_id:`t${i}`, group_id:'g', session_id:'s', speaker_name:'甲', original_text:text, effective_text:text,
    start:`2026-09-08T00:00:0${i}Z`, created_at:`2026-09-08T00:00:0${i}Z`, is_corrected:i===1,
    correction_id:i===1?'c1':null, correction_reason:i===1?'AI 整场匹配':null,
    source_transcript_ids:[`t${i}`], is_merged:false, final_excluded:i===2,
  }))
  await page.route('**/api/admin/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/admin/')) return route.continue()
    if (route.request().method() !== 'GET') throw new Error('Read-only test must not write data')
    let json: unknown = {}
    if (path.endsWith('/groups')) json = [group]
    else if (path.endsWith('/sessions')) json = [session]
    else if (path.endsWith('/transcripts')) json = {items:rows, meta:{total:4,page:1,page_size:500}}
    else if (path.endsWith('/utterances')) json = {session_id:'s',group_id:'g',utterances:[{order_index:1,content:'完整录音正文',start_time:1}]}
    await route.fulfill({json})
  })
  await page.goto('/admin/assisted-transcript-corrections')
  for (let i=0;i<2;i++) {
    await page.getByRole('button', {name:'查看旧版逐条修订'}).click()
    await expect(page.getByText('最终修订版本',{exact:true})).toBeVisible()
    const final = page.locator('.final-version-list')
    await expect(final.getByText('完整录音正文',{exact:true})).toBeVisible()
    await expect(final.getByText('前面的原文',{exact:true})).toBeVisible()
    await expect(final.getByText('后面的原文',{exact:true})).toBeVisible()
    await expect(final.getByText('中间胡乱识别不能进入正文',{exact:true})).toHaveCount(0)
    await expect(page.locator('.transcript-list').getByText('中间胡乱识别不能进入正文',{exact:true})).toBeVisible()
    await expect(page.getByText('未进入正文 1 条',{exact:true})).toBeVisible()
    if (i===0) await page.reload()
  }
})
