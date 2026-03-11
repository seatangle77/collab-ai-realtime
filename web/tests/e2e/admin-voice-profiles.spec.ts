import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

/** 登录并进入声纹管理页 */
async function loginAsAdminAndGoToVoiceProfiles(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
  await page.goto('/admin/voice-profiles')
  await expect(page.getByRole('heading', { name: '用户声纹管理' })).toBeVisible()
}

type VoiceProfileFixture = {
  userId: string
  profileId: string
  userEmail: string
  userName: string
  sampleCount: number
  hasEmbedding: boolean
}

/** 通过 App 端注册用户并创建声纹配置（可选样本与声纹） */
async function createVoiceProfileViaAppApi(options: {
  label: string
  sampleCount?: number
  generateEmbedding?: boolean
}): Promise<VoiceProfileFixture> {
  const { label, sampleCount = 0, generateEmbedding = false } = options
  const email = `e2e-voice-${label}-${Date.now()}@example.com`
  const password = '1234'
  const name = `声纹用户-${label}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      email,
      password,
      device_token: `device-${label}`,
    }),
  })
  if (!regRes.ok) throw new Error(`register failed: ${regRes.status} ${await regRes.text()}`)
  const user = (await regRes.json()) as { id: string }

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error(`login failed: ${loginRes.status} ${await loginRes.text()}`)
  const { access_token: token } = (await loginRes.json()) as { access_token: string }

  // GET /api/voice-profile/me 会创建空 profile
  const meRes = await fetch(`${API_BASE}/api/voice-profile/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!meRes.ok) throw new Error(`voice-profile/me failed: ${meRes.status} ${await meRes.text()}`)
  const profile = (await meRes.json()) as { id: string; sample_audio_urls: string[] }

  let finalSampleCount = 0
  if (sampleCount > 0) {
    const urls = Array.from({ length: sampleCount }, (_, i) => `https://example.com/e2e-${label}-${i}.wav`)
    const putRes = await fetch(`${API_BASE}/api/voice-profile/me/samples`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ sample_audio_urls: urls }),
    })
    if (!putRes.ok) throw new Error(`samples put failed: ${putRes.status} ${await putRes.text()}`)
    const updated = (await putRes.json()) as { sample_audio_urls: string[] }
    finalSampleCount = updated.sample_audio_urls?.length ?? 0
  }

  let hasEmbedding = false
  if (generateEmbedding && finalSampleCount > 0) {
    const genRes = await fetch(`${API_BASE}/api/voice-profile/me/generate-embedding`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (genRes.ok) hasEmbedding = true
  }

  return {
    userId: user.id,
    profileId: profile.id,
    userEmail: email,
    userName: name,
    sampleCount: finalSampleCount,
    hasEmbedding,
  }
}

const shared: {
  withSamples: VoiceProfileFixture
  withEmbedding: VoiceProfileFixture
  noSamples: VoiceProfileFixture
} = {} as any

test.describe.serial('Admin 声纹管理 - 主流程', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdminAndGoToVoiceProfiles(page)
  })

  test('0. 造数：创建无样本、有样本无声纹、有样本有声纹三条声纹', async () => {
    shared.noSamples = await createVoiceProfileViaAppApi({ label: 'NoSamples', sampleCount: 0 })
    shared.withSamples = await createVoiceProfileViaAppApi({
      label: 'WithSamples',
      sampleCount: 2,
      generateEmbedding: false,
    })
    shared.withEmbedding = await createVoiceProfileViaAppApi({
      label: 'WithEmbedding',
      sampleCount: 2,
      generateEmbedding: true,
    })
    expect(shared.noSamples.profileId).toBeTruthy()
    expect(shared.withSamples.sampleCount).toBe(2)
    expect(shared.withEmbedding.hasEmbedding).toBe(true)
  })

  test('1. 列表加载：表头、筛选、分页可见', async ({ page }) => {
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('heading', { name: '用户声纹管理' })).toBeVisible()
    await expect(page.getByPlaceholder('按用户 ID 精确查询')).toBeVisible()
    await expect(page.getByRole('button', { name: '查询' })).toBeVisible()
    await expect(page.getByRole('button', { name: '重置' })).toBeVisible()
    await expect(page.locator('.admin-voice-profiles-table .el-table')).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '用户 ID' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '样本数量' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '声纹状态' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '操作' })).toBeVisible()
  })

  test('2. 按用户 ID 精确查询', async ({ page }) => {
    await page.getByPlaceholder('按用户 ID 精确查询').fill(shared.withSamples.userId)
    await page.getByRole('button', { name: '查询' }).click()
    const row = page.getByRole('row').filter({ hasText: shared.withSamples.userId }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText(shared.withSamples.userEmail)
  })

  test('3. 筛选「有样本」', async ({ page }) => {
    await page.locator('.admin-voice-profiles-filters .el-select').first().click()
    await page.getByRole('option', { name: '有样本' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const bodyRows = page.locator('.admin-voice-profiles-table .el-table__body tbody tr')
    await expect(bodyRows.first()).toBeVisible({ timeout: 10000 })
    const count = await bodyRows.count()
    expect(count).toBeGreaterThanOrEqual(2)
    await expect(page.getByRole('row').filter({ hasText: shared.withSamples.userId }).first()).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: shared.withEmbedding.userId }).first()).toBeVisible()
  })

  test('4. 筛选「无样本」', async ({ page }) => {
    await page.locator('.admin-voice-profiles-filters .el-select').first().click()
    await page.getByRole('option', { name: '无样本' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const row = page.getByRole('row').filter({ hasText: shared.noSamples.userId }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('0')
  })

  test('5. 筛选「已生成」声纹', async ({ page }) => {
    await page.locator('.admin-voice-profiles-filters .el-select').nth(1).click()
    await page.getByRole('option', { name: '已生成' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const row = page.getByRole('row').filter({ hasText: shared.withEmbedding.userId }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('已生成')
  })

  test('6. 筛选「未生成」声纹', async ({ page }) => {
    await page.locator('.admin-voice-profiles-filters .el-select').nth(1).click()
    await page.getByRole('option', { name: '未生成' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.getByRole('row').filter({ hasText: shared.withEmbedding.userId })).toHaveCount(0)
    const row = page.getByRole('row').filter({ hasText: shared.withSamples.userId }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('未生成')
  })

  test('7. 重置筛选', async ({ page }) => {
    await page.getByPlaceholder('按用户 ID 精确查询').fill(shared.withSamples.userId)
    await page.locator('.admin-voice-profiles-filters .el-select').first().click()
    await page.getByRole('option', { name: '有样本' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    await page.getByRole('button', { name: '重置' }).click()
    await expect(page.getByPlaceholder('按用户 ID 精确查询')).toHaveValue('')
    await expect(page.locator('.admin-voice-profiles-table .el-table__body tbody tr').first()).toBeVisible()
  })

  test('8. 从列表进入详情', async ({ page }) => {
    await page.getByPlaceholder('按用户 ID 精确查询').fill(shared.withSamples.userId)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.locator('.admin-voice-profiles-table .el-table__body tbody tr').first()).toBeVisible({ timeout: 10000 })
    const row = page.locator('.admin-voice-profiles-table .el-table__body tbody tr').filter({
      has: page.getByRole('cell', { name: shared.withSamples.userId, exact: true }),
    }).first()
    await row.getByRole('button', { name: '查看详情' }).click()
    await expect(page).toHaveURL(new RegExp(`/admin/voice-profiles/${shared.withSamples.profileId}`))
    await expect(page.getByText('声纹配置详情').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '返回列表' })).toBeVisible()
  })

  test('9. 详情页展示用户与样本列表', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.withSamples.profileId}`)
    await expect(page.getByText('声纹配置详情').first()).toBeVisible()
    await expect(page.getByText(shared.withSamples.userId)).toBeVisible()
    await expect(page.getByText('样本列表').first()).toBeVisible()
    await expect(page.getByText('声纹状态').first()).toBeVisible()
    await expect(page.getByPlaceholder('输入样本 URL')).toBeVisible()
    await expect(page.getByRole('button', { name: '添加样本' })).toBeVisible()
    await expect(page.getByRole('button', { name: '保存样本列表' })).toBeVisible()
    await expect(page.getByRole('button', { name: '重新生成声纹' })).toBeVisible()
  })

  test('10. 返回列表并保持页码/筛选', async ({ page }) => {
    await page.goto('/admin/voice-profiles')
    await page.getByRole('button', { name: '查询' }).click()
    const pagination = page.locator('.admin-voice-profiles-pagination')
    const hasPager = await pagination.locator('.el-pager').isVisible().catch(() => false)
    if (hasPager) {
      await pagination.locator('.el-pager li').nth(1).click()
      await expect(page).toHaveURL(/\?.*page=2/)
    }
    await page.getByPlaceholder('按用户 ID 精确查询').fill(shared.withSamples.userId)
    await page.getByRole('button', { name: '查询' }).click()
    await expect(page.locator('.admin-voice-profiles-table .el-table__body tbody tr').first()).toBeVisible({ timeout: 10000 })
    const row = page.locator('.admin-voice-profiles-table .el-table__body tbody tr').filter({
      has: page.getByRole('cell', { name: shared.withSamples.userId, exact: true }),
    }).first()
    await row.getByRole('button', { name: '查看详情' }).click()
    await expect(page).toHaveURL(new RegExp(`/admin/voice-profiles/${shared.withSamples.profileId}`))
    await page.getByRole('button', { name: '返回列表' }).click()
    await expect(page).toHaveURL(/\/admin\/voice-profiles/)
    await expect(page.getByPlaceholder('按用户 ID 精确查询')).toHaveValue(shared.withSamples.userId)
  })

  test('10.1 详情边界：无样本空状态可添加', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.noSamples.profileId}`)
    await expect(page.getByText('暂无样本，请在下行添加 URL。')).toBeVisible()
    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/one.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 1')).toBeVisible()
  })

  test('10.2 详情：无样本时点重新生成提示', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.noSamples.profileId}`)
    await page.getByRole('button', { name: '重新生成声纹' }).click()
    await expect(page.getByText('当前没有任何样本，请先添加样本 URL 后再生成声纹')).toBeVisible()
  })

  test('11. 详情：添加样本并保存', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.noSamples.profileId}`)
    await expect(page.getByText('暂无样本，请在下行添加 URL。')).toBeVisible()
    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/e2e-new.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 1')).toBeVisible()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText('样本列表已保存')).toBeVisible({ timeout: 15000 })
  })

  test('12. 详情：有样本时重新生成声纹（确认）', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.withSamples.profileId}`)
    await expect(page.getByText('未生成').first()).toBeVisible()
    await page.getByRole('button', { name: '重新生成声纹' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: '生成' }).click()
    await expect(page.getByText('声纹已生成')).toBeVisible()
    await expect(page.getByText('已生成').first()).toBeVisible()
  })

  test('13. 详情：重新生成时取消确认', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.withEmbedding.profileId}`)
    await expect(page.getByText('已生成').first()).toBeVisible()
    await page.getByRole('button', { name: '重新生成声纹' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: '取消' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await expect(page.getByText('已生成').first()).toBeVisible()
  })

  test('14. 列表边界：用户 ID 查无结果', async ({ page }) => {
    await page.getByPlaceholder('按用户 ID 精确查询').fill('00000000-0000-0000-0000-000000000000')
    await page.getByRole('button', { name: '查询' }).click()
    const bodyRows = page.locator('.admin-voice-profiles-table .el-table__body tbody tr')
    await expect(bodyRows).toHaveCount(0)
  })

  test('15. 列表边界：组合筛选无结果', async ({ page }) => {
    await page.getByPlaceholder('按用户 ID 精确查询').fill(shared.withEmbedding.userId)
    await page.locator('.admin-voice-profiles-filters .el-select').nth(1).click()
    await page.getByRole('option', { name: '未生成' }).click()
    await page.getByRole('button', { name: '查询' }).click()
    const bodyRows = page.locator('.admin-voice-profiles-table .el-table__body tbody tr')
    await expect(bodyRows).toHaveCount(0)
  })

  test('16. 列表边界：分页切换每页条数', async ({ page }) => {
    await page.getByRole('button', { name: '查询' }).click()
    const pagination = page.locator('.admin-voice-profiles-pagination')
    if (!(await pagination.isVisible())) return
    const sizeSelect = pagination.locator('.el-select').first()
    if (!(await sizeSelect.isVisible())) return
    await sizeSelect.click()
    await page.getByRole('option', { name: '10' }).click()
    await expect(page).toHaveURL(/\?.*page_size=10/)
  })

  test('17. 详情边界：添加空 URL 提示', async ({ page }) => {
    await page.goto(`/admin/voice-profiles/${shared.withSamples.profileId}`)
    await page.getByPlaceholder('输入样本 URL').fill('')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('请输入非空的样本 URL')).toBeVisible()
  })

  test('18. 详情异常：访问不存在的 profile id', async ({ page }) => {
    await page.goto('/admin/voice-profiles/00000000-0000-0000-0000-000000000000')
    await expect(
      page.getByText(/声纹配置不存在|加载声纹配置详情失败|404/),
    ).toBeVisible({ timeout: 10000 })
  })
})
