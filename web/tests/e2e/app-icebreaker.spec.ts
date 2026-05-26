import { test, expect, type Page } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

interface AppTestUser {
  email: string
  password: string
  name: string
}

async function registerUserForE2E(label: string): Promise<AppTestUser> {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  const email = `app-icebreaker-${label}-${unique}@example.com`
  const password = '1234'
  const name = `破冰测试用户-${label}`

  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!res.ok) throw new Error(`注册失败: ${res.status} ${await res.text()}`)
  return { email, password, name }
}

async function loginAndGetToken(user: AppTestUser): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: user.email, password: user.password }),
  })
  if (!res.ok) throw new Error(`登录失败: ${res.status} ${await res.text()}`)
  const data = (await res.json()) as { access_token: string }
  return data.access_token
}

async function createGroupAsUser(user: AppTestUser, name: string): Promise<{ id: string; name: string }> {
  const token = await loginAndGetToken(user)
  const res = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`创建群组失败: ${res.status} ${await res.text()}`)
  const data = await res.json()
  return { id: data.group.id as string, name: data.group.name as string }
}

async function loginViaUI(page: Page, user: AppTestUser) {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

async function setupFakeMediaRecorder(page: Page) {
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
                // no-op
              },
            },
          ]
        },
      } as unknown as MediaStream
    }

    class FakeMediaRecorder {
      stream: MediaStream
      state: RecordingState = 'inactive'
      ondataavailable: ((event: BlobEvent) => void) | null = null
      onstop: (() => void) | null = null

      static isTypeSupported() {
        return true
      }

      constructor(stream: MediaStream) {
        this.stream = stream
      }

      start() {
        this.state = 'recording'
        const blob = new Blob(['fake-icebreaker-audio'], { type: 'audio/webm' })
        this.ondataavailable?.({ data: blob } as BlobEvent)
      }

      stop() {
        this.state = 'inactive'
        this.onstop?.()
      }
    }

    // @ts-expect-error assign polyfill
    window.MediaRecorder = FakeMediaRecorder
  })
}

function multipartHas(body: string, field: string, value: string): boolean {
  return body.includes(`name="${field}"`) && body.includes(value)
}

test.describe('App 破冰声纹采样', () => {
  test('Phase 1 和 Phase 2 都调用破冰声纹采样接口', async ({ page }) => {
    const user = await registerUserForE2E('voice-sample')
    const group = await createGroupAsUser(user, `破冰声纹群-${Date.now()}`)
    const voiceSampleRequests: string[] = []

    await setupFakeMediaRecorder(page)
    await page.route('**/api/icebreaker/voice-sample', async (route) => {
      const body = route.request().postDataBuffer()?.toString('utf8') || ''
      voiceSampleRequests.push(body)
      const isIntro = multipartHas(body, 'source', 'intro')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          text: isIntro ? `我是${user.name}` : '故事继续往前走',
          voice_sample_added: true,
          sample_url: 'http://127.0.0.1:8000/audio/voice-profiles/mock.wav',
          warnings: [],
        }),
      })
    })

    await loginViaUI(page, user)
    await page.evaluate((groupObj) => {
      window.localStorage.setItem('app_current_group', JSON.stringify(groupObj))
    }, group)

    await page.goto('/app/icebreaker')
    await expect(page.getByRole('heading', { name: '破冰时间' })).toBeVisible()
    await page.getByRole('button', { name: '开始破冰' }).click()

    await page.getByRole('button', { name: /开始录音/ }).click()
    await page.getByRole('button', { name: /停止录音|保存中/ }).click()
    await expect(page.getByText('录得很好，继续下一题吧')).toBeVisible()

    await page.getByRole('button', { name: '阶段二 · 故事接龙' }).click()
    await page.getByRole('button', { name: '开始接龙' }).click()
    await page.getByRole('button', { name: /开始接龙/ }).click()
    await page.getByRole('button', { name: /停止接龙|转写中/ }).click()
    await expect(page.getByText(`${user.name} 的故事片段已转写`)).toBeVisible()

    expect(voiceSampleRequests.length).toBeGreaterThanOrEqual(2)
    expect(voiceSampleRequests.some((body) => multipartHas(body, 'source', 'intro'))).toBeTruthy()
    expect(voiceSampleRequests.some((body) => multipartHas(body, 'source', 'story'))).toBeTruthy()
  })
})
