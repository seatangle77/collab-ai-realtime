import { expect, test } from '@playwright/test'


test('整场 AI 匹配必须先对齐，并可预览后批量保存', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('admin_api_key', 'test-admin-key')
  })

  const group = {
    group_id: 'g1',
    group_name: '测试小组',
    condition: 'glasses',
    transcript_count: 4,
    corrected_count: 1,
  }
  const session = {
    session_id: 's1',
    session_title: '测试会话',
    group_id: 'g1',
    group_name: '测试小组',
    condition: 'glasses',
    transcript_count: 4,
    corrected_count: 1,
    created_at: '2026-09-07T10:00:00+08:00',
    started_at: '2026-09-07T10:00:00+08:00',
  }
  const transcripts = [
    {
      transcript_id: 'tr0', group_id: 'g1', session_id: 's1', speaker_user_id: null,
      speaker_name: '成员乙', original_text: '人工修订前', effective_text: '这是之前保存的人工修订。',
      start: '2026-09-07T10:00:05+08:00', end: '2026-09-07T10:00:07+08:00',
      created_at: '2026-09-07T10:00:05+08:00', is_corrected: true,
      correction_id: 'manual1', correction_reason: '人工核对', corrected_by: '研究员',
      corrected_at: '2026-09-07T10:05:00+08:00', source_transcript_ids: ['tr0'], is_merged: false,
    },
    {
      transcript_id: 'tr1', group_id: 'g1', session_id: 's1', speaker_user_id: null,
      speaker_name: '成员甲', original_text: '这是实时', effective_text: '这是实时',
      start: '2026-09-07T10:00:10+08:00', end: '2026-09-07T10:00:12+08:00',
      created_at: '2026-09-07T10:00:10+08:00', is_corrected: false,
      correction_id: null, correction_reason: null, corrected_by: null, corrected_at: null,
      source_transcript_ids: ['tr1'], is_merged: false,
    },
    {
      transcript_id: 'tr2', group_id: 'g1', session_id: 's1', speaker_user_id: null,
      speaker_name: '成员甲', original_text: '转写碎片', effective_text: '转写碎片',
      start: '2026-09-07T10:00:12+08:00', end: '2026-09-07T10:00:14+08:00',
      created_at: '2026-09-07T10:00:12+08:00', is_corrected: false,
      correction_id: null, correction_reason: null, corrected_by: null, corrected_at: null,
      source_transcript_ids: ['tr2'], is_merged: false,
    },
    {
      transcript_id: 'tr3', group_id: 'g1', session_id: 's1', speaker_user_id: null,
      speaker_name: '成员甲', original_text: '测试测试无对应录音', effective_text: '测试测试无对应录音',
      start: '2026-09-07T10:02:00+08:00', end: '2026-09-07T10:02:02+08:00',
      created_at: '2026-09-07T10:02:00+08:00', is_corrected: false,
      correction_id: null, correction_reason: null, corrected_by: null, corrected_at: null,
      source_transcript_ids: ['tr3'], is_merged: false,
    },
  ]
  const match = {
    match_id: 'aim1',
    reference_orders: [1],
    transcript_ids: ['tr1', 'tr2'],
    reference_text: '这是人工确认的准确文本。',
    transcript_text: '这是实时 转写碎片',
    corrected_text: '这是人工确认的准确文本。',
    confidence: 0.93,
    confidence_level: 'high',
    time_distance_seconds: 0,
    reason: '语义、时间和顺序一致',
    saved: false,
    review_required: true,
    review_reason: '请确认当前分组边界',
  }
  const completedRun = {
    run_id: 'air1', session_id: 's1', model: 'qwen3-max', status: 'completed',
    completed_chunks: 1, total_chunks: 1, matches: [match], failed_chunks: [],
    message: '匹配完成', total_tokens: 1200, created_at: '2026-09-07T10:10:00+08:00',
    out_of_scope_transcript_ids: [],
    summary: {
      high: 1, medium: 0, low: 0, unmatched_references: 0,
      unmatched_transcripts: 0, skipped_corrected_transcripts: 0,
      replaceable_ai_transcripts: 0,
      organized_transcripts: 2, total_target_transcripts: 2,
      review_required: 1, out_of_scope_transcripts: 0,
    },
  }
  let currentRun = completedRun
  let saved = false
  const currentTranscripts = () => saved
    ? transcripts.map(item => ['tr0', 'tr3'].includes(item.transcript_id) ? item : ({
      ...item,
      effective_text: '这是人工确认的准确文本。',
      is_corrected: true,
      correction_id: 'stc1',
      correction_reason: 'AI 整场匹配（qwen3-max，可信度 0.930）',
      corrected_at: '2026-09-07T10:11:00+08:00',
      source_transcript_ids: ['tr1', 'tr2'],
      is_merged: true,
    }))
    : transcripts

  await page.route('**/api/admin/transcript-corrections/groups', route =>
    route.fulfill({ json: [group] }))
  await page.route('**/api/admin/transcript-corrections/sessions?*', route =>
    route.fulfill({ json: [session] }))
  await page.route('**/api/admin/transcript-corrections/sessions/s1/transcripts?*', route =>
    route.fulfill({ json: { items: currentTranscripts(), meta: { total: 4, page: 1, page_size: 500 } } }))
  await page.route('**/api/admin/coi-transcript-coding/sessions/s1/utterances', route =>
    route.fulfill({ json: {
      session_id: 's1', group_id: 'g1',
      utterances: [{ order_index: 1, content: '这是人工确认的准确文本。', start_time: 20, coi_category: null }],
    } }))
  await page.route('**/api/admin/transcript-corrections/sessions/s1/ai-match-runs', async (route) => {
    const request = route.request()
    expect(request.method()).toBe('POST')
    expect((await request.postDataJSON()).anchor).toEqual({
      transcript_id: 'tr1', transcript_relative_seconds: 10,
      reference_order: 1, reference_start_time: 20,
    })
    await route.fulfill({ json: { ...completedRun, status: 'queued', completed_chunks: 0, matches: [] } })
  })
  await page.route('**/api/admin/transcript-corrections/ai-match-runs/air1', route =>
    route.fulfill({ json: currentRun }))

  let savePayload: unknown = null
  await page.route('**/api/admin/transcript-corrections/ai-match-runs/air1/save', async (route) => {
    savePayload = await route.request().postDataJSON()
    saved = true
    currentRun = { ...currentRun, matches: [{ ...match, saved: true }] }
    await route.fulfill({ json: {
      saved_matches: 1, saved_transcripts: 2, saved_match_ids: ['aim1'], skipped: [],
    } })
  })

  await page.goto('/admin/assisted-transcript-corrections')

  const startButton = page.getByRole('button', { name: '自动整理整场', exact: true })
  await expect(startButton).toBeDisabled()
  await page.locator('.transcript-row', { hasText: '这是实时' }).click()
  await page.locator('.reference-row').first().click()
  await page.getByRole('button', { name: '以当前两条设为对齐起点' }).click()
  await expect(startButton).toBeEnabled()

  await startButton.click()
  await page.getByRole('dialog').getByRole('button', { name: '开始整理' }).click()
  await expect(page.getByText('已整理 2 / 2 条')).toBeVisible()
  await expect(page.getByText('这是人工确认的准确文本。').first()).toBeVisible()
  await expect(page.getByText('可选检查 1 处', { exact: true })).toBeVisible()
  await expect(page.getByText('不需要逐条手动修订')).toBeVisible()
  await expect(page.getByRole('button', { name: '直接保存整场修订', exact: true })).toBeEnabled()
  await expect(page.getByText('修订文本', { exact: true })).not.toBeVisible()

  await page.getByRole('button', { name: '直接保存整场修订', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '保存整场修订' }).click()
  await expect.poll(() => savePayload).not.toBeNull()
  expect(savePayload).toEqual({ match_ids: ['aim1'], corrected_by: null })
  await expect(page.getByText('最终修订版本')).toBeVisible()
  await expect(page.locator('.final-version-list').getByText('这是人工确认的准确文本。')).toBeVisible()
  await expect(page.locator('.final-version-list').getByText('这是之前保存的人工修订。')).toBeVisible()
  await expect(page.locator('.final-version-list').getByText('测试测试无对应录音')).toHaveCount(0)
  await expect(page.getByText('未进入正文 1 条')).toBeVisible()
  await page.getByText('查看未进入最终正文的实时转写（1 条）').click()
  await expect(page.locator('.excluded-originals').getByText('测试测试无对应录音')).toBeVisible()
  await expect(page.getByText('原有人工修订 1')).toBeVisible()
  await expect(page.getByText('由 2 条实时转写合并')).toBeVisible()
})
