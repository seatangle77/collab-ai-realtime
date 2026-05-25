import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const MAX_UPLOAD_FILE_SIZE = 50 * 1024 * 1024

test.describe.configure({ mode: 'serial' })

interface AppTestUser {
  email: string
  password: string
  name: string
}

async function registerUserForE2E(label: string): Promise<AppTestUser> {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  const email = `app-voice-${label}-${unique}@example.com`
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

async function createAppVoiceUser(options: {
  label: string
  sampleCount?: number
  generateEmbedding?: boolean
}): Promise<AppTestUser & { sampleCount: number; hasEmbedding: boolean }> {
  const { label, sampleCount = 0, generateEmbedding = false } = options
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  const email = `app-voice-fixture-${label}-${unique}@example.com`
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
        this.ondataavailable?.(event)
      }

      stop() {
        this.onstop?.()
      }
    }

    // @ts-expect-error assign polyfill
    window.MediaRecorder = FakeMediaRecorder as any
  })
}

function makeAudioFilePayload(name = 'sample.m4a', content = 'fake-audio') {
  return {
    name,
    mimeType: 'audio/mp4',
    buffer: Buffer.from(content),
  }
}

async function createOversizeAudioFile(): Promise<string> {
  const filePath = path.join(os.tmpdir(), `voice-profile-oversize-${Date.now()}.flac`)
  const handle = await fs.open(filePath, 'w')
  try {
    await handle.truncate(MAX_UPLOAD_FILE_SIZE + 1)
  } finally {
    await handle.close()
  }
  return filePath
}

function messageLocator(page: import('@playwright/test').Page, text: string | RegExp) {
  return page.locator('.el-message__content').filter({ hasText: text }).last()
}

test.describe('App 我的声纹 - 鉴权与初始展示', () => {
  test('未登录访问声纹页会跳转到登录页', async ({ page }) => {
    await page.goto('/app/voice-profile')
    await expect(page).toHaveURL(/\/app\/login/)
    await expect(page).toHaveURL(/redirect=\/app\/voice-profile/)
  })

  test('新用户进入页面展示空状态和两个音频入口', async ({ page }) => {
    const user = await registerUserForE2E('empty')
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await expect(page.getByRole('heading', { name: '我的声纹' })).toBeVisible()
    await expect(page.getByText('录制或上传音频样本，生成专属声纹用于说话人识别。')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '现场录音' })).toBeVisible()
    await expect(page.getByRole('button', { name: '粘贴 URL' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '上传文件' })).toBeVisible()
    await expect(page.getByText('暂无样本')).toBeVisible()
    await expect(page.getByText('已添加 0 / 5 条样本')).toBeVisible()
    await expect(page.getByRole('button', { name: '生成声纹' })).toBeDisabled()
  })
})

test.describe.skip('App 我的声纹 - URL 样本（入口已从移动端页面移除）', () => {
  test('可以通过 URL 添加样本并自动保存', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'url-add' })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '现场录音' }).click()
    await page.getByPlaceholder('请输入音频 URL').fill('https://example.com/one.wav')
    await page.getByRole('button', { name: '添加' }).click()

    await expect(messageLocator(page, '已保存')).toBeVisible()
    await expect(page.getByText('已添加 1 / 5 条样本')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(1)
    await expect(page.locator('.sample-row audio')).toHaveCount(1)
  })

  test('按回车添加 URL，输入框会被清空', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'url-enter' })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '现场录音' }).click()
    const input = page.getByPlaceholder('请输入音频 URL')
    await input.fill('https://example.com/enter.wav')
    await input.press('Enter')

    await expect(messageLocator(page, '已保存')).toBeVisible()
    await expect(input).toHaveValue('')
    await expect(page.locator('.sample-row')).toHaveCount(1)
  })

  test('空 URL 和纯空格 URL 会提示', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'url-empty' })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '粘贴 URL' }).click()
    await page.getByRole('button', { name: '添加' }).click()
    await expect(messageLocator(page, '请输入非空的样本 URL')).toBeVisible()

    await page.getByPlaceholder('请输入音频 URL').fill('   ')
    await page.getByRole('button', { name: '添加' }).click()
    await expect(messageLocator(page, '请输入非空的样本 URL')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(0)
  })

  test('达到 5 条样本后不能继续添加 URL', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'url-full', sampleCount: 5 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '粘贴 URL' }).click()
    await page.getByPlaceholder('请输入音频 URL').fill('https://example.com/extra.wav')
    await page.getByRole('button', { name: '添加' }).click()

    await expect(messageLocator(page, '已达到最多 5 条样本')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(5)
    await expect(page.getByText('已添加 5 / 5 条样本')).toBeVisible()
  })

  test('删除样本会自动保存并更新列表', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'url-delete' })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '粘贴 URL' }).click()
    await page.getByPlaceholder('请输入音频 URL').fill('https://example.com/delete-1.wav')
    await page.getByRole('button', { name: '添加' }).click()
    await expect(messageLocator(page, '已保存')).toBeVisible()

    await page.getByPlaceholder('请输入音频 URL').fill('https://example.com/delete-2.wav')
    await page.getByRole('button', { name: '添加' }).click()
    await expect(messageLocator(page, '已保存')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(2)

    await page.getByRole('button', { name: '删除第 1 条样本' }).click()

    await expect(messageLocator(page, '已保存')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(1)
    await expect(page.getByText('已添加 1 / 5 条样本')).toBeVisible()
  })
})

test.describe('App 我的声纹 - 现场录音', () => {
  test('录音上传成功后会追加到样本列表', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'record-ok' })
    await setupFakeMediaRecorder(page)
    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ url: 'https://example.com/e2e-record-ok.wav' }),
      }),
    )

    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '开始录音' }).click()
    await page.getByRole('button', { name: '停止录音' }).click()
    await expect(page.locator('.preview-audio')).toBeVisible()

    await page.getByRole('button', { name: '添加此段' }).click()
    await expect(page.getByText('录音已上传并添加到样本列表')).toBeVisible()
    await expect(page.getByText('已添加 1 / 5 条样本')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(1)
  })

  test('录音上传失败时展示错误', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'record-fail' })
    await setupFakeMediaRecorder(page)
    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({ status: 500, body: 'upload error' }),
    )

    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '开始录音' }).click()
    await page.getByRole('button', { name: '停止录音' }).click()
    await page.getByRole('button', { name: '添加此段' }).click()

    await expect(messageLocator(page, /上传录音失败|upload error/)).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(0)
  })

  test('样本已满时不能继续录音', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'record-full', sampleCount: 5 })
    await setupFakeMediaRecorder(page)
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await expect(page.getByRole('button', { name: '开始录音' })).toBeDisabled()
  })
})

test.describe('App 我的声纹 - 上传文件', () => {
  test('上传文件成功后会显示预览并追加样本', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'file-ok' })
    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ url: 'https://example.com/e2e-upload-ok.m4a' }),
      }),
    )

    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()
    await page.locator('input[type="file"]').setInputFiles(makeAudioFilePayload())

    await expect(page.getByText('sample.m4a')).toBeVisible()
    await expect(page.getByText('10 B')).toBeVisible()
    await expect(page.locator('.preview-audio')).toBeVisible()

    await page.getByRole('button', { name: '上传此文件' }).click()
    await expect(messageLocator(page, '文件已上传并添加到样本列表')).toBeVisible()
    await expect(page.getByText('已添加 1 / 5 条样本')).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(1)
  })

  test('切换离开上传文件 Tab 会清空已选文件', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'file-reset' })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()
    await page.locator('input[type="file"]').setInputFiles(makeAudioFilePayload('reset.m4a'))
    await expect(page.getByText('reset.m4a')).toBeVisible()

    await page.getByRole('button', { name: '粘贴 URL' }).click()
    await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()

    await expect(page.getByText('reset.m4a')).toHaveCount(0)
    await expect(page.locator('.preview-audio')).toHaveCount(0)
  })

  test('超过 50MB 的文件会被前端拦截且不会发起上传', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'file-oversize' })
    let uploadRequestCount = 0
    const oversizedFilePath = await createOversizeAudioFile()

    try {
      await page.route('**/api/voice-profile/me/upload-audio', async (route) => {
        uploadRequestCount += 1
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ url: 'https://example.com/should-not-upload.m4a' }),
        })
      })

      await loginViaUI(page, user)
      await page.goto('/app/voice-profile')

      await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()
      await page.locator('input[type="file"]').setInputFiles(oversizedFilePath)

      await page.getByRole('button', { name: '上传此文件' }).click()

      await expect(messageLocator(page, '文件不能超过 50MB')).toBeVisible()
      await expect(page.locator('.sample-row')).toHaveCount(0)
      expect(uploadRequestCount).toBe(0)
    } finally {
      await fs.unlink(oversizedFilePath).catch(() => undefined)
    }
  })

  test('上传文件接口失败时展示错误', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'file-fail' })
    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({ status: 500, body: 'file upload error' }),
    )

    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()
    await page.locator('input[type="file"]').setInputFiles(makeAudioFilePayload('fail.m4a'))
    await page.getByRole('button', { name: '上传此文件' }).click()

    await expect(messageLocator(page, /上传文件失败|file upload error/)).toBeVisible()
    await expect(page.locator('.sample-row')).toHaveCount(0)
  })

  test('样本已满时上传文件入口禁用', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'file-full', sampleCount: 5 })
    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()
    await expect(page.locator('.file-drop-area')).toBeDisabled()
  })
})

test.describe('App 我的声纹 - 生成声纹与异常', () => {
  test('有样本时可以生成并重新生成声纹', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'embedding', sampleCount: 1 })
    let generateCount = 0

    await page.route('**/api/voice-profile/me/generate-embedding', async (route) => {
      generateCount += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'mock-voice-profile-id',
          user_id: 'mock-user-id',
          sample_audio_urls: ['https://example.com/e2e-embedding-0.wav'],
          created_at: '2026-01-01T00:00:00Z',
          voice_embedding: [0.1, 0.2, 0.3],
          embedding_status: 'ready',
          embedding_updated_at: generateCount === 1 ? '2026-01-01T00:00:00Z' : '2026-01-01T00:10:00Z',
        }),
      })
    })

    await loginViaUI(page, user)
    await page.goto('/app/voice-profile')

    await page.getByRole('button', { name: '生成声纹' }).click()
    await expect(page.locator('.embedding-done')).toBeVisible()
    await expect(page.getByText('声纹已生成').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '重新生成' })).toBeVisible()

    await page.getByRole('button', { name: '重新生成' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('dialog').getByRole('button', { name: '生成' }).click()
    await expect(messageLocator(page, '声纹已重新生成')).toBeVisible()
  })

  test('加载失败时显示错误消息', async ({ page }) => {
    const user = await registerUserForE2E('err-me')
    await loginViaUI(page, user)

    await page.route('**/api/voice-profile/me', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 500, body: 'load error' })
        return
      }
      await route.continue()
    })

    await page.goto('/app/voice-profile')
    await expect(messageLocator(page, /加载声纹失败|load error/)).toBeVisible()
  })

  test('保存样本失败时显示错误消息', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'err-save' })
    await loginViaUI(page, user)
    await page.route('**/api/voice-profile/me/upload-audio', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ url: 'https://example.com/error.wav' }),
      }),
    )
    await page.route('**/api/voice-profile/me/samples', async (route) => {
      if (route.request().method() === 'PUT') {
        await route.fulfill({ status: 500, body: 'save error' })
        return
      }
      await route.continue()
    })

    await page.goto('/app/voice-profile')
    await page.locator('.record-tab').filter({ hasText: '上传文件' }).click()
    await page.locator('input[type="file"]').setInputFiles(makeAudioFilePayload('error.m4a'))
    await page.getByRole('button', { name: '上传此文件' }).click()

    await expect(messageLocator(page, /保存样本列表失败|save error/)).toBeVisible()
  })

  test('生成声纹失败时显示错误消息', async ({ page }) => {
    const user = await createAppVoiceUser({ label: 'err-generate', sampleCount: 1 })
    await loginViaUI(page, user)
    await page.route('**/api/voice-profile/me/generate-embedding', (route) =>
      route.fulfill({ status: 500, body: 'generate error' }),
    )

    await page.goto('/app/voice-profile')
    await page.getByRole('button', { name: '生成声纹' }).click()

    await expect(messageLocator(page, /生成声纹失败|generate error/)).toBeVisible()
  })
})
