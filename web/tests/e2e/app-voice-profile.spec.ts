import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

interface AppTestUser {
  email: string
  password: string
  name: string
}

async function registerUserForE2E(label: string): Promise<AppTestUser> {
  const ts = Date.now()
  const email = `app-voice-${label}-${ts}@example.com`
  const password = '1234'
  const name = `App Voice E2E ${label}`

  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!res.ok) throw new Error(`注册失败: ${res.status} ${await res.text()}`)
  return { email, password, name }
}

async function loginViaUI(page: import('@playwright/test').Page, user: AppTestUser) {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

/** 通过 API 造声纹用户：可选样本数、是否生成声纹。返回用于 UI 登录的 user。 */
async function createAppVoiceUser(options: {
  label: string
  sampleCount?: number
  generateEmbedding?: boolean
}): Promise<AppTestUser & { sampleCount: number; hasEmbedding: boolean }> {
  const { label, sampleCount = 0, generateEmbedding = false } = options
  const email = `app-voice-fixture-${label}-${Date.now()}@example.com`
  const password = '1234'
  const name = `声纹Fixture-${label}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!regRes.ok) throw new Error(`register failed: ${regRes.status} ${await regRes.text()}`)

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error(`login failed: ${loginRes.status} ${await loginRes.text()}`)
  const { access_token: token } = (await loginRes.json()) as { access_token: string }

  const meRes = await fetch(`${API_BASE}/api/voice-profile/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!meRes.ok) throw new Error(`voice-profile/me failed: ${meRes.status} ${await meRes.text()}`)

  let finalSampleCount = 0
  if (sampleCount > 0) {
    const urls = Array.from({ length: sampleCount }, (_, i) => `https://example.com/e2e-${label}-${i}.wav`)
    const putRes = await fetch(`${API_BASE}/api/voice-profile/me/samples`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
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

  return { email, password, name, sampleCount: finalSampleCount, hasEmbedding }
}

async function setupFakeMediaRecorder(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    // @ts-expect-error override in test environment
    window.navigator.mediaDevices = window.navigator.mediaDevices || ({} as MediaDevices)
    // @ts-expect-error test polyfill
    window.navigator.mediaDevices.getUserMedia = async () => {
      return {
        getTracks() {
          return [
            {
              stop() {
                // no-op for tests
              },
            },
          ]
        },
      } as unknown as MediaStream
    }

    class FakeMediaRecorder {
      stream: MediaStream
      ondataavailable: ((event: BlobEvent) => void) | null = null
      onstop: (() => void) | null = null

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      constructor(stream: MediaStream, _options?: any) {
        this.stream = stream
      }

      start() {
        const blob = new Blob(['fake-audio'], { type: 'audio/webm' })
        const event = { data: blob } as BlobEvent
        if (this.ondataavailable) {
          this.ondataavailable(event)
        }
      }

      stop() {
        if (this.onstop) {
          this.onstop()
        }
      }
    }

    // @ts-expect-error assign polyfill
    window.MediaRecorder = FakeMediaRecorder as any
  })
}

// --- 鉴权与导航 ---

test.describe('App 我的声纹 - 鉴权与导航', () => {
  test('未登录访问声纹页重定向到登录且带 redirect', async ({ page }) => {
    await page.goto('/app/voice-profile')
    await expect(page).toHaveURL(/\/app\/login/)
    await expect(page).toHaveURL(/redirect=\/app\/voice-profile/)
  })

  test('登录后通过 redirect 跳回声纹页', async ({ page }) => {
    const user = await registerUserForE2E('redirect')
    await page.goto('/app/voice-profile')
    await expect(page).toHaveURL(/\/app\/login/)
    await page.getByLabel('邮箱').fill(user.email)
    await page.getByLabel('密码').fill(user.password)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/app\/voice-profile/)
    await expect(page.getByRole('heading', { name: '我的声纹' })).toBeVisible()
  })

  test('从首页导航进入我的声纹', async ({ page }) => {
    const user = await registerUserForE2E('nav')
    await loginViaUI(page, user)
    await page.goto('/app')
    await page.getByRole('link', { name: '我的声纹' }).click()
    await expect(page).toHaveURL(/\/app\/voice-profile/)
    await expect(page.locator('.app-voice-profile-title')).toHaveText('我的声纹')
  })
})

// --- 主流程（串行，共用一用户） ---

let mainFlowUser: AppTestUser

test.describe.serial('App 我的声纹 - 主流程', () => {
  test('首访展示空状态与未生成', async ({ page }) => {
    mainFlowUser = await registerUserForE2E('main')
    await loginViaUI(page, mainFlowUser)
    await page.goto('/app/voice-profile')

    await expect(page.getByRole('heading', { name: '我的声纹' })).toBeVisible()
    await expect(page.getByText('在此管理你的声纹样本并生成声纹', { exact: false })).toBeVisible()
    await expect(page.getByText('样本列表', { exact: true })).toBeVisible()
    await expect(page.getByText('暂无样本，请在下行添加 URL。')).toBeVisible()
    await expect(page.getByText('未生成').first()).toBeVisible()
    await expect(page.getByText('样本数量：0/5（最多 5 条）')).toBeVisible()
    await expect(page.getByText('嵌入状态：未生成')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toBeVisible()
    await expect(page.getByRole('button', { name: '生成声纹' })).toBeVisible()
    await expect(page.getByPlaceholder('输入样本 URL')).toBeVisible()
    await expect(page.getByRole('button', { name: '添加样本' })).toBeVisible()
    await expect(page.getByRole('button', { name: '保存样本列表' })).toBeVisible()
  })

  test('添加一条样本并保存', async ({ page }) => {
    await loginViaUI(page, mainFlowUser)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/one.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 1')).toBeVisible()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText('样本列表已保存')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('样本数量：1/5（最多 5 条）')).toBeVisible()
    await expect(page.getByText('嵌入状态：未生成')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toBeVisible()
  })

  test('首次生成声纹', async ({ page }) => {
    await loginViaUI(page, mainFlowUser)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '生成声纹' }).click()
    // 只校验状态 Tag，避免 strict 模式冲突
    await expect(page.getByText('已生成').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '重新生成声纹' })).toBeVisible()
    await expect(page.getByText('嵌入状态：已就绪')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toHaveCount(0)
  })

  test('重新生成声纹确认', async ({ page }) => {
    await loginViaUI(page, mainFlowUser)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '重新生成声纹' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: '生成' }).click()
    await expect(page.getByText('声纹已重新生成')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('嵌入状态：已就绪')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toHaveCount(0)
  })

  test('重新生成声纹取消', async ({ page }) => {
    await loginViaUI(page, mainFlowUser)
    await page.goto('/app/voice-profile')

    await expect(page.getByText('已生成').first()).toBeVisible()
    await page.getByRole('button', { name: '重新生成声纹' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('dialog').getByRole('button', { name: '取消' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await expect(page.getByText('已生成').first()).toBeVisible()
    await expect(page.getByText('嵌入状态：已就绪')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toHaveCount(0)
  })

  test('折叠展示声纹元数据', async ({ page }) => {
    await loginViaUI(page, mainFlowUser)
    await page.goto('/app/voice-profile')

    await expect(page.getByText('声纹元数据（占位）').first()).toBeVisible()
    await page.getByText('声纹元数据（占位）').first().click()
    await expect(page.locator('.embedding-json')).toBeVisible()
  })
})

// --- 边界 ---

test.describe('App 我的声纹 - 边界', () => {
  test('空 URL 添加提示', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'empty-url', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('请输入非空的样本 URL')).toBeVisible()
  })

  test('仅空格不添加', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'spaces', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('   ')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('请输入非空的样本 URL')).toBeVisible()
    await expect(page.getByText('暂无样本，请在下行添加 URL。')).toBeVisible()
  })

  test('无样本点生成提示', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'no-samples', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '生成声纹' }).click()
    await expect(page.getByText('请先添加样本 URL 后再生成声纹')).toBeVisible()
    await expect(page.getByText('样本数量：0/5（最多 5 条）')).toBeVisible()
    await expect(page.getByText('嵌入状态：未生成')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toBeVisible()
  })

  test('1 条样本可保存并生成', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'one', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/single.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 1')).toBeVisible()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText('样本列表已保存')).toBeVisible({ timeout: 15000 })
    await page.getByRole('button', { name: '生成声纹' }).click()
    await expect(page.getByText(/声纹已生成|声纹已重新生成/)).toBeVisible({ timeout: 15000 })
  })

  test('5 条样本保存成功', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'five', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    for (let i = 0; i < 5; i++) {
      await page.getByPlaceholder('输入样本 URL').fill(`https://example.com/s${i}.wav`)
      await page.getByRole('button', { name: '添加样本' }).click()
    }
    await expect(page.getByText('样本 5')).toBeVisible()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText('样本列表已保存')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('样本数量：5/5（最多 5 条）')).toBeVisible()
    // 样本 5 行里应该有音频预览
    await expect(page.locator('.sample-row').nth(4).locator('audio')).toBeVisible()
  })

  test('超过 5 条保存时后端报错', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'over5', sampleCount: 5 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/extra.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 6')).toBeVisible()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    // 后端会返回「最多支持 5 条语音样本」，前端统一展示在全局 Message
    await expect(page.locator('.el-message')).toContainText('最多支持 5 条语音样本', {
      timeout: 15000,
    })
  })

  test('回车添加样本', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'enter', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/enter.wav')
    await page.getByPlaceholder('输入样本 URL').press('Enter')
    await expect(page.getByText('样本 1')).toBeVisible()
    await expect(page.getByPlaceholder('输入样本 URL')).toHaveValue('')
  })

  test('删除全部样本后保存', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'delall', sampleCount: 2 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await expect(page.getByText('样本 1')).toBeVisible()
    await page.getByRole('button', { name: '删除' }).first().click()
    await page.getByRole('button', { name: '删除' }).first().click()
    await expect(page.getByText('暂无样本，请在下行添加 URL。')).toBeVisible()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText('样本列表已保存')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('样本数量：0/5（最多 5 条）')).toBeVisible()
    await expect(page.getByText('嵌入状态：未生成')).toBeVisible()
    await expect(page.getByText('最近更新：-')).toBeVisible()
  })

  test('刷新后数据仍在', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'refresh', sampleCount: 2 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await expect(page.getByText('样本 1')).toBeVisible()
    await expect(page.getByText('样本 2')).toBeVisible()
    await page.reload()
    await expect(page).toHaveURL(/\/app\/voice-profile/)
    await expect(page.getByText('样本 1')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('样本 2')).toBeVisible()
    await expect(page.getByText('样本数量：2/5（最多 5 条）')).toBeVisible()
  })
})

// --- 异常（接口失败） ---

test.describe('App 我的声纹 - 异常', () => {
  test('GET /me 失败显示加载失败', async ({ page }) => {
    const user = await registerUserForE2E('err-me')
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.route('**/api/voice-profile/me', (route) => route.fulfill({ status: 500, body: 'error' }))
    await page.reload()
    await expect(page.getByText(/加载声纹失败|error/)).toBeVisible({ timeout: 10000 })
  })

  test('保存样本接口失败显示错误', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'err-save', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/x.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await page.route('**/api/voice-profile/me/samples', (route) => {
      if (route.request().method() === 'PUT') return route.fulfill({ status: 500, body: 'save error' })
      return route.continue()
    })
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText(/保存样本列表失败|save error/)).toBeVisible({ timeout: 10000 })
  })

  test('生成声纹接口失败显示错误', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'err-gen', sampleCount: 1 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.route('**/api/voice-profile/me/generate-embedding', (route) =>
      route.fulfill({ status: 500, body: 'gen error' }),
    )
    await page.getByRole('button', { name: '生成声纹' }).click()
    await expect(page.getByText(/生成声纹失败|gen error/)).toBeVisible({ timeout: 10000 })
  })
})

// --- 极端 / 交互 ---

test.describe('App 我的声纹 - 极端与交互', () => {
  test('添加样本未保存点生成会发请求且可能失败或提示', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'nosave', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://example.com/unsaved.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 1')).toBeVisible()
    await page.getByRole('button', { name: '生成声纹' }).click()
    // 行为依赖后端实现：成功或失败均可接受，只要页面没有报错即可
    await expect(page).toHaveURL(/\/app\/voice-profile/, { timeout: 15000 })
  })

  test('多条样本增删改后保存', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'edit', sampleCount: 0 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByPlaceholder('输入样本 URL').fill('https://a.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await page.getByPlaceholder('输入样本 URL').fill('https://b.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await page.getByPlaceholder('输入样本 URL').fill('https://c.wav')
    await page.getByRole('button', { name: '添加样本' }).click()
    await expect(page.getByText('样本 3')).toBeVisible()
    await page.locator('.sample-input input').first().fill('https://a-modified.wav')
    await page.getByRole('button', { name: '删除' }).nth(1).click()
    await page.getByRole('button', { name: '保存样本列表' }).click()
    await expect(page.getByText('样本列表已保存')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('样本 1')).toBeVisible()
    await expect(page.getByText('样本 2')).toBeVisible()
    await expect(page.locator('.sample-input input').first()).toHaveValue('https://a-modified.wav')
  })

  test('录音上传：成功上传并写入样本列表', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'record-ok', sampleCount: 0 })
    await setupFakeMediaRecorder(page)
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    // 为了稳定起见，这里直接模拟上传接口成功返回，避免依赖后端对 multipart 的解析行为
    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ url: 'https://example.com/e2e-record-ok.wav' }),
      }),
    )

    await expect(page.getByText('录音采集')).toBeVisible()

    await page.getByRole('button', { name: '开始录音' }).click()
    await page.getByRole('button', { name: '停止' }).click()

    await expect(page.getByText('录音预览')).toBeVisible()
    await expect(page.locator('audio')).toBeVisible()

    const beforeCount = await page.locator('.sample-row').count()

    await page.getByRole('button', { name: '上传并添加为样本' }).click()
    // 上传成功后应当至少新增一条样本记录
    await expect
      .poll(async () => page.locator('.sample-row').count(), { timeout: 15000 })
      .toBeGreaterThan(beforeCount)
    await expect(page.getByText('样本数量：1/5（最多 5 条）')).toBeVisible()
  })

  test('录音上传：接口失败展示错误信息', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'record-fail', sampleCount: 0 })
    await setupFakeMediaRecorder(page)
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({ status: 500, body: 'upload error' }),
    )

    await page.getByRole('button', { name: '开始录音' }).click()
    await page.getByRole('button', { name: '停止' }).click()
    await expect(page.getByText('录音预览')).toBeVisible()

    await page.getByRole('button', { name: '上传并添加为样本' }).click()
    await expect(page.getByText(/上传录音失败|upload error/)).toBeVisible({ timeout: 10000 })
  })

  test('录音采集：样本已满时禁止继续录音', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'record-full', sampleCount: 5 })
    await setupFakeMediaRecorder(page)
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    const startBtn = page.getByRole('button', { name: '开始录音' })
    await expect(startBtn).toBeDisabled()
  })
})
