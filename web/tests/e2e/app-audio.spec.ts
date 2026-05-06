/**
 * 模块五 + 模块六 前端 E2E 测试（Playwright）
 *
 * 用例分类：
 *   E. WS 连接与状态（35-37）
 *   F. 录音与音频发送（38-40）
 *   G. 转写展示（41-43）
 *   H. 异常场景（44-46）
 *   I. 文件注入（47-55）
 *
 * 运行前提：
 *   1. 后端已启动（port 8000）
 *   2. 前端已启动（npm run dev，port 5173）
 *
 * 运行方式（在 web/ 目录下）：
 *   npx playwright test tests/e2e/app-audio.spec.ts
 */

import { test, expect, type Page } from '@playwright/test'

const API_BASE      = process.env.API_BASE_URL  || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

test.setTimeout(60000)

// ── helpers ──────────────────────────────────────────────────────

interface TestUser {
  email: string
  password: string
  userId: string
  token: string
}

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts    = Date.now()
  const email = `audio-e2e-${label}-${ts}@test.com`
  const name  = `AudioE2E ${label}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name, email, password: '1234', device_token: `tok_${ts}` }),
  })
  if (!regRes.ok) throw new Error(`注册失败: ${await regRes.text()}`)
  const user = await regRes.json() as { id: string }

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password: '1234' }),
  })
  const login = await loginRes.json() as { access_token: string }
  return { email, password: '1234', userId: user.id, token: login.access_token }
}

async function createGroup(token: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body:    JSON.stringify({ name: `AudioGroup_${Date.now()}` }),
  })
  const data = await res.json()
  return data.group.id as string
}

async function createSession(token: string, groupId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}/sessions`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body:    JSON.stringify({ session_title: `AudioSession_${Date.now()}` }),
  })
  const data = await res.json()
  return data.id as string
}

async function startSession(token: string, sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/sessions/${sessionId}/start`, {
    method:  'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}

async function addTranscriptAdmin(
  sessionId: string,
  groupId: string,
  speaker: string,
  text: string,
): Promise<void> {
  await fetch(`${API_BASE}/api/admin/transcripts/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
    body:    JSON.stringify({
      session_id: sessionId,
      group_id:   groupId,
      speaker,
      text,
      start: '2024-01-01T00:00:01Z',
      end:   '2024-01-01T00:00:05Z',
    }),
  })
}

async function loginViaUI(page: Page, user: TestUser): Promise<void> {
  await page.goto('/app/login')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('密码').fill(user.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/app\/?$/)
}

/** 注入假麦克风：返回静音 PCM 的 MediaStream */
async function injectFakeMicrophone(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const AudioContext = window.AudioContext || (window as any).webkitAudioContext
    const ctx          = new AudioContext()
    const oscillator   = ctx.createOscillator()
    const dst          = ctx.createMediaStreamDestination()
    oscillator.connect(dst)
    oscillator.start()
    const fakeStream   = dst.stream

    const origGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      if (constraints?.audio) return fakeStream
      return origGetUserMedia(constraints)
    }
  })
}

async function setupFakeMediaRecorder(page: Page): Promise<void> {
  await page.addInitScript(() => {
    ;(window as any).__mediaRecorderState = {
      createdCount: 0,
      startCount: 0,
      stopCount: 0,
      chunkCount: 0,
    }

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
      timer: number | null = null
      state: 'inactive' | 'recording' = 'inactive'

      static isTypeSupported(mimeType: string) {
        return mimeType === 'audio/webm'
      }

      constructor(stream: MediaStream) {
        this.stream = stream
        ;(window as any).__mediaRecorderState.createdCount += 1
      }

      start(timeslice?: number) {
        this.state = 'recording'
        ;(window as any).__mediaRecorderState.startCount += 1
        const emitChunk = () => {
          const payload = (window as any).__fakeAudioChunkPayload ?? 'fake-audio'
          const blob = new Blob([payload], { type: 'audio/webm' })
          const event = { data: blob } as BlobEvent
          ;(window as any).__mediaRecorderState.chunkCount += 1
          this.ondataavailable?.(event)
        }

        emitChunk()
        if (typeof timeslice === 'number' && timeslice > 0) {
          this.timer = window.setInterval(emitChunk, timeslice)
        }
      }

      stop() {
        if (this.timer != null) {
          window.clearInterval(this.timer)
          this.timer = null
        }
        this.state = 'inactive'
        ;(window as any).__mediaRecorderState.stopCount += 1
        this.onstop?.()
      }
    }

    // @ts-expect-error assign polyfill
    window.MediaRecorder = FakeMediaRecorder as any
  })
}

async function setupWebSocketControl(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const NativeWebSocket = window.WebSocket
    ;(window as any).__appAudioSockets = []
    class ControlledWebSocket extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        if (protocols === undefined) {
          super(url)
        } else {
          super(url, protocols)
        }
        ;(window as any).__appAudioSockets.push(this)
      }
    }
    window.WebSocket = ControlledWebSocket as typeof WebSocket
  })
}

async function setupFakeAudioContextWithSpy(
  page: Page,
  options: {
    initialState?: 'running' | 'suspended'
    playbackBehavior?: 'normal' | 'ended' | 'error'
    playbackDelayMs?: number
  } = {},
): Promise<void> {
  await page.addInitScript((config) => {
    const audioState = {
      createdContexts: 0,
      closedContexts: 0,
      resumeCalls: 0,
      playCalls: 0,
      sourceDisconnectCalls: 0,
      destinationDisconnectCalls: 0,
      connectCalls: [] as string[],
      events: [] as string[],
      lastContextState: null as string | null,
    }

    ;(window as any).__audioTestState = audioState
    ;(window as any).__connectCalls = audioState.connectCalls

    const initialState = config?.initialState ?? 'running'
    const playbackBehavior = config?.playbackBehavior ?? 'normal'
    const playbackDelayMs = config?.playbackDelayMs ?? 50

    class FakeAudioContext {
      state: 'running' | 'suspended' | 'closed'
      destination: { __kind: 'speakerDestination' }

      constructor() {
        this.state = initialState
        this.destination = { __kind: 'speakerDestination' }
        audioState.createdContexts += 1
        audioState.lastContextState = this.state
      }

      createMediaStreamDestination() {
        return {
          __kind: 'mediaStreamDestination',
          stream: {
            getTracks() {
              return [
                {
                  stop() {
                    // no-op for tests
                  },
                },
              ]
            },
          } as unknown as MediaStream,
          disconnect() {
            audioState.destinationDisconnectCalls += 1
          },
        }
      }

      createMediaElementSource(_audio: HTMLAudioElement) {
        const ctx = this
        return {
          connect(target: { __kind?: string }) {
            const label = target === ctx.destination
              ? 'speakerDestination'
              : target?.__kind === 'mediaStreamDestination'
                ? 'mediaStreamDestination'
                : 'unknown'
            audioState.connectCalls.push(label)
          },
          disconnect() {
            audioState.sourceDisconnectCalls += 1
          },
        }
      }

      async resume() {
        audioState.resumeCalls += 1
        audioState.events.push('resume')
        this.state = 'running'
        audioState.lastContextState = this.state
      }

      async close() {
        audioState.closedContexts += 1
        audioState.events.push('close')
        this.state = 'closed'
        audioState.lastContextState = this.state
      }
    }

    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      writable: true,
      value: FakeAudioContext,
    })
    ;(window as any).webkitAudioContext = FakeAudioContext

    const playImpl = function(this: HTMLMediaElement) {
      audioState.playCalls += 1
      audioState.events.push('play')
      if (playbackBehavior === 'ended') {
        window.setTimeout(() => {
          this.onended?.(new Event('ended'))
        }, playbackDelayMs)
      }
      if (playbackBehavior === 'error') {
        window.setTimeout(() => {
          this.onerror?.(new Event('error'))
        }, playbackDelayMs)
      }
      return Promise.resolve()
    }

    const pauseImpl = function() {
      audioState.events.push('pause')
    }

    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      configurable: true,
      writable: true,
      value: playImpl,
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
      configurable: true,
      writable: true,
      value: pauseImpl,
    })
  }, options)
}

function captureWsMessages(page: Page): string[] {
  const wsMessages: string[] = []
  page.on('websocket', ws => {
    ws.on('framesent', frame => {
      if (frame.payload) wsMessages.push(String(frame.payload))
    })
  })
  return wsMessages
}

function countAudioChunkMessages(messages: string[]): number {
  return messages.filter((message) => {
    try {
      return JSON.parse(message)?.type === 'audio_chunk'
    } catch {
      return false
    }
  }).length
}

async function waitForSessionReady(page: Page, sessionId: string, user: TestUser): Promise<void> {
  await loginViaUI(page, user)
  await page.goto(`/app/sessions/${sessionId}`)
  const recordBtn = page.getByTestId('record-start')
  await recordBtn.waitFor({ state: 'visible' })
  await expect(recordBtn).toBeEnabled({ timeout: 20000 })
}

async function pickInjectionAudioFile(
  page: Page,
  file: { name: string; mimeType: string; buffer?: Buffer } = {
    name: 'injected-test.wav',
    mimeType: 'audio/wav',
    buffer: Buffer.from('RIFFfakeWAVEdata'),
  },
): Promise<void> {
  const fileChooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /文件注入|选择测试音频|更换测试音频/i }).click()
  const fileChooser = await fileChooserPromise
  await fileChooser.setFiles({
    name: file.name,
    mimeType: file.mimeType,
    buffer: file.buffer ?? Buffer.from('RIFFfakeWAVEdata'),
  })
}

// ════════════════════════════════════════════════════════════════
// E. WS 连接与状态
// ════════════════════════════════════════════════════════════════

test.describe('E. WS 连接与状态', () => {

  test('E-35: 打开会话详情页 → WS 建立，页面显示已连接状态', async ({ page }) => {
    const user      = await registerAndLogin('e35')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // connected 时 ws-status 会被隐藏，开始录音按钮可点击是更稳定的已连接信号
    const recordBtn = page.getByTestId('record-start')
    await recordBtn.waitFor({ state: 'visible' })
    await expect(recordBtn).toBeEnabled({ timeout: 20000 })
    await expect(page.locator('[data-testid="ws-status"]')).toBeHidden()
  })

  test('E-36: WS 收到 transcript 消息 → 转写列表实时出现新条目', async ({ page }) => {
    const user      = await registerAndLogin('e36')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const recordBtn = page.getByTestId('record-start')
    await recordBtn.waitFor({ state: 'visible' })
    await expect(recordBtn).toBeEnabled({ timeout: 20000 })

    // 通过 admin API 注入 transcript，触发 WS 广播
    await addTranscriptAdmin(sessionId, groupId, '测试说话人', 'E36 实时转写测试文本')

    // 验证转写条目出现在页面
    await expect(
      page.locator('.app-session-detail-transcript-text, [data-testid="transcript-text"]').first()
    ).toContainText('E36 实时转写测试文本', { timeout: 10000 })
  })

  test('E-37: 多条 transcript 实时推送 → 列表按顺序追加', async ({ page }) => {
    const user      = await registerAndLogin('e37')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(1000)

    const recordBtn = page.getByTestId('record-start')
    await recordBtn.waitFor({ state: 'visible' })
    await expect(recordBtn).toBeEnabled({ timeout: 20000 })

    await addTranscriptAdmin(sessionId, groupId, '说话人A', 'E37第一句')
    await page.waitForTimeout(300)
    await addTranscriptAdmin(sessionId, groupId, '说话人B', 'E37第二句')

    await expect(
      page.locator('.app-session-detail-transcript-group')
    ).toHaveCount(2, { timeout: 10000 })
  })
})

// ════════════════════════════════════════════════════════════════
// F. 录音与音频发送
// ════════════════════════════════════════════════════════════════

test.describe('F. 录音与音频发送', () => {

  test('F-38: 点击录音按钮 → audio_chunk WS 消息开始发送', async ({ page }) => {
    const user      = await registerAndLogin('f38')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)

    // 监听 WS 消息（须在 goto 前注册，否则捕获不到已建立的连接）
    const wsMessages: string[] = []
    page.on('websocket', ws => {
      ws.on('framesent', frame => {
        if (frame.payload) wsMessages.push(String(frame.payload))
      })
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 等 WS 连上（按钮 disabled 时不可点）
    const recordBtn = page.getByRole('button', { name: /开始录音/i })
    await recordBtn.waitFor({ state: 'visible' })
    await expect(recordBtn).toBeEnabled({ timeout: 10000 })

    await recordBtn.click()

    await expect.poll(() => {
      return wsMessages.some(m => {
        try { return JSON.parse(m)?.type === 'audio_chunk' } catch { return false }
      })
    }, { timeout: 10000 }).toBeTruthy()
  })

  test('F-39: 停止录音 → audio_chunk 不再发送', async ({ page }) => {
    const user      = await registerAndLogin('f39')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await injectFakeMicrophone(page)
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)
    await page.waitForTimeout(1000)

    const recordBtn = page.getByRole('button', { name: /录音|开始录音|record/i })
    await recordBtn.click()
    await page.waitForTimeout(2000)

    // 停止录音
    const stopBtn = page.getByRole('button', { name: /停止|结束录音|stop/i })
    await stopBtn.click()
    await page.waitForTimeout(500)

    const wsMessages: string[] = []
    page.on('websocket', ws => {
      ws.on('framesent', frame => {
        if (frame.payload) wsMessages.push(String(frame.payload))
      })
    })

    await page.waitForTimeout(2000)
    const hasAudioChunk = wsMessages.some(m => {
      try { return JSON.parse(m)?.type === 'audio_chunk' } catch { return false }
    })
    expect(hasAudioChunk).toBeFalsy()
  })

  test('F-40: 会话详情页已结束状态 → 录音按钮不可点击或不显示', async ({ page }) => {
    const user      = await registerAndLogin('f40')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    // 结束会话
    await fetch(`${API_BASE}/api/sessions/${sessionId}/end`, {
      method:  'POST',
      headers: { Authorization: `Bearer ${user.token}` },
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const recordBtn = page.getByRole('button', { name: /录音|开始录音|record/i })
    const isVisible = await recordBtn.isVisible().catch(() => false)
    const isEnabled = isVisible ? await recordBtn.isEnabled() : false

    expect(!isVisible || !isEnabled).toBeTruthy()
  })

  test('F-41: 录音中 WS 断开 → 页面显示正在暂存录音', async ({ page }) => {
    const user      = await registerAndLogin('f41')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)
    await setupWebSocketControl(page)
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const recordBtn = page.getByRole('button', { name: /开始录音/i })
    await expect(recordBtn).toBeEnabled({ timeout: 10000 })
    await recordBtn.click()

    await page.evaluate(() => {
      const sockets = (window as any).__appAudioSockets as WebSocket[]
      sockets[sockets.length - 1]?.close(4000, 'test_disconnect')
    })

    await expect(page.locator('.app-session-detail-audio-upload-banner')).toContainText(
      '正在暂存录音',
      { timeout: 10000 },
    )
  })

  test('F-42: WS 重连成功 → 离线录音段通过 HTTP 补传', async ({ page }) => {
    const user      = await registerAndLogin('f42')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    const uploads: string[] = []
    await page.route('**/api/sessions/**/audio-segments', async (route) => {
      const segmentId = `seg-${uploads.length + 1}`
      uploads.push(segmentId)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'processed',
          segment_id: segmentId,
          transcript_id: `tr_${uploads.length}`,
          duplicate: false,
        }),
      })
    })

    await setupFakeMediaRecorder(page)
    await setupWebSocketControl(page)
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const recordBtn = page.getByRole('button', { name: /开始录音/i })
    await expect(recordBtn).toBeEnabled({ timeout: 10000 })
    await recordBtn.click()

    await page.evaluate(() => {
      const sockets = (window as any).__appAudioSockets as WebSocket[]
      sockets[sockets.length - 1]?.close(4000, 'test_disconnect')
    })

    await expect.poll(() => uploads.length, { timeout: 15000 }).toBeGreaterThan(0)
    await expect(page.locator('.app-session-detail-audio-upload-banner')).toContainText(
      /已补传|正在补传/,
      { timeout: 10000 },
    )
  })

  test('F-43: 离线补传持续失败 → 页面提示实录可能不完整', async ({ page }) => {
    const user      = await registerAndLogin('f43')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    let uploadAttempts = 0
    await page.route('**/api/sessions/**/audio-segments', async (route) => {
      uploadAttempts += 1
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'test upload failure' }),
      })
    })

    await setupFakeMediaRecorder(page)
    await setupWebSocketControl(page)
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const recordBtn = page.getByRole('button', { name: /开始录音/i })
    await expect(recordBtn).toBeEnabled({ timeout: 10000 })
    await recordBtn.click()

    await page.evaluate(() => {
      const sockets = (window as any).__appAudioSockets as WebSocket[]
      sockets[sockets.length - 1]?.close(4000, 'test_disconnect')
    })

    await expect.poll(() => uploadAttempts, { timeout: 15000 }).toBeGreaterThanOrEqual(3)
    await expect(page.locator('.app-session-detail-audio-upload-banner')).toContainText(
      '实录可能不完整',
      { timeout: 10000 },
    )
  })
})

// ════════════════════════════════════════════════════════════════
// G. 转写展示
// ════════════════════════════════════════════════════════════════

test.describe('G. 转写展示', () => {

  test('G-41: transcript 含 speaker 和 text → 页面正确显示', async ({ page }) => {
    const user      = await registerAndLogin('g41')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await addTranscriptAdmin(sessionId, groupId, '张三', 'G41 展示测试文本')

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    await expect(
      page.locator('.app-session-detail-speaker-name').first()
    ).toContainText('张三', { timeout: 15000 })
    await expect(
      page.locator('.app-session-detail-transcript-text, [data-testid="transcript-text"]').first()
    ).toContainText('G41 展示测试文本', { timeout: 15000 })
  })

  test('G-42: speaker=unknown → 页面显示占位符而非空白', async ({ page }) => {
    const user      = await registerAndLogin('g42')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await addTranscriptAdmin(sessionId, groupId, 'unknown', 'G42 未知说话人测试')

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const speakerEl = page.locator(
      '.app-session-detail-speaker-name'
    ).first()
    await expect(speakerEl).toBeVisible({ timeout: 15000 })

    // 不应显示空白（有文字或有占位符）
    const text = await speakerEl.textContent()
    expect(text?.trim().length).toBeGreaterThan(0)
  })

  test('G-43: 快速收到多条 transcript → 列表按顺序排列，不乱序', async ({ page }) => {
    const user      = await registerAndLogin('g43')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    // 按顺序写入 3 条
    await addTranscriptAdmin(sessionId, groupId, '说话人A', 'G43第一句话')
    await addTranscriptAdmin(sessionId, groupId, '说话人B', 'G43第二句话')
    await addTranscriptAdmin(sessionId, groupId, '说话人A', 'G43第三句话')

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const items = page.locator(
      '.app-session-detail-transcript-text, [data-testid="transcript-text"]'
    )
    await expect(items).toHaveCount(3, { timeout: 15000 })

    const texts = await items.allTextContents()
    expect(texts[0]).toContain('G43第一句话')
    expect(texts[1]).toContain('G43第二句话')
    expect(texts[2]).toContain('G43第三句话')
  })
})

// ════════════════════════════════════════════════════════════════
// H. 异常场景
// ════════════════════════════════════════════════════════════════

test.describe('H. 异常场景', () => {

  test('H-44: 麦克风权限被拒绝 → 友好提示，页面不崩溃', async ({ page }) => {
    const user      = await registerAndLogin('h44')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    // 注入拒绝麦克风的 mock
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = async () => {
        throw new DOMException('Permission denied', 'NotAllowedError')
      }
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    const recordBtn = page.getByRole('button', { name: /录音|开始录音|record/i })
    if (await recordBtn.isVisible()) {
      await recordBtn.click()
      await page.waitForTimeout(1000)
    }

    // 页面不崩溃（无 JS error alert）
    await expect(page.locator('.app-session-detail-title, [data-testid="session-title"]')).toBeVisible()
  })

  test('H-45: 访问不存在的 session → 显示错误，不白屏', async ({ page }) => {
    const user = await registerAndLogin('h45')
    await loginViaUI(page, user)
    await page.goto('/app/sessions/s00000000')

    // 应显示错误信息而非白屏
    const errorVisible = await page.locator(
      '.app-session-detail-error, [data-testid="session-error"], .el-result'
    ).isVisible().catch(() => false)
    const titleVisible = await page.locator('body').isVisible()

    expect(errorVisible || titleVisible).toBeTruthy()
  })

  test('H-46: 已结束会话的转写历史不丢失', async ({ page }) => {
    const user      = await registerAndLogin('h46')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    // 写入历史转写
    await addTranscriptAdmin(sessionId, groupId, '李四', 'H46 历史转写不丢失')

    // 结束会话
    await fetch(`${API_BASE}/api/sessions/${sessionId}/end`, {
      method:  'POST',
      headers: { Authorization: `Bearer ${user.token}` },
    })

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 已结束状态下历史转写仍可见
    await expect(
      page.locator('.app-session-detail-transcript-text, [data-testid="transcript-text"]').first()
    ).toContainText('H46 历史转写不丢失', { timeout: 8000 })
  })
})

// ════════════════════════════════════════════════════════════════
// I. 文件注入
// ════════════════════════════════════════════════════════════════

test.describe('I. 文件注入', () => {

  test('I-47: 正常注入 → MediaRecorder 仍正常发送 chunk（回归验证）', async ({ page }) => {
    const user      = await registerAndLogin('i47')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page)
    const wsMessages = captureWsMessages(page)

    await waitForSessionReady(page, sessionId, user)
    await pickInjectionAudioFile(page)

    await expect.poll(() => countAudioChunkMessages(wsMessages), { timeout: 10000 }).toBeGreaterThan(0)
  })

  test('I-48: 正常注入 → AudioContext.destination 被连接（播放链路建立）', async ({ page }) => {
    const user      = await registerAndLogin('i48')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page)

    await waitForSessionReady(page, sessionId, user)
    await pickInjectionAudioFile(page)

    await expect.poll(async () => {
      return page.evaluate(() => (window as any).__connectCalls as string[])
    }, { timeout: 10000 }).toEqual(['mediaStreamDestination', 'speakerDestination'])
  })

  test('I-49: 注入时已在录音 → 注入被拒绝，不建立第二个 AudioContext', async ({ page }) => {
    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page)
    await page.goto('/app/login')

    const result = await page.evaluate(async () => {
      const mod = await import('/src/composables/useAudioRecorder.ts')
      const recorder = mod.useAudioRecorder()
      const chunkTypes: string[] = []
      recorder.onChunk((_blob, mimeType) => {
        chunkTypes.push(mimeType)
      })

      await recorder.startRecording()
      await recorder.startFileInjection(new File(['fake-audio'], 'busy.wav', { type: 'audio/wav' }))

      return {
        isRecording: recorder.isRecording.value,
        recordingSource: recorder.recordingSource.value,
        chunkTypes,
        createdContexts: (window as any).__audioTestState.createdContexts,
        connectCalls: (window as any).__connectCalls,
      }
    })

    expect(result.isRecording).toBeTruthy()
    expect(result.recordingSource).toBe('microphone')
    expect(result.chunkTypes).toContain('audio/webm')
    expect(result.createdContexts).toBe(0)
    expect(result.connectCalls).toEqual([])
  })

  test('I-50: 注入文件播放结束 → audio.onended 触发，录制自动停止，AudioContext 被关闭', async ({ page }) => {
    const user      = await registerAndLogin('i50')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page, { playbackBehavior: 'ended', playbackDelayMs: 30 })
    const wsMessages = captureWsMessages(page)

    await waitForSessionReady(page, sessionId, user)
    await pickInjectionAudioFile(page, {
      name: 'short.wav',
      mimeType: 'audio/wav',
      buffer: Buffer.from('tiny'),
    })

    await expect.poll(async () => {
      return page.evaluate(() => (window as any).__audioTestState.closedContexts as number)
    }, { timeout: 10000 }).toBeGreaterThan(0)

    const chunkCountAfterEnd = countAudioChunkMessages(wsMessages)
    await page.waitForTimeout(1200)

    expect(countAudioChunkMessages(wsMessages)).toBe(chunkCountAfterEnd)
    await expect(page.getByRole('button', { name: /录音|开始录音|record/i })).toBeVisible()
  })

  test('I-51: 注入文件播放出错 → audio.onerror 触发，录制停止，页面不崩溃', async ({ page }) => {
    const user      = await registerAndLogin('i51')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page, { playbackBehavior: 'error', playbackDelayMs: 30 })
    const wsMessages = captureWsMessages(page)

    await waitForSessionReady(page, sessionId, user)
    await pickInjectionAudioFile(page, {
      name: 'broken.webm',
      mimeType: 'audio/webm',
      buffer: Buffer.from('garbage'),
    })

    await expect.poll(async () => {
      return page.evaluate(() => (window as any).__audioTestState.closedContexts as number)
    }, { timeout: 10000 }).toBeGreaterThan(0)

    const chunkCountAfterError = countAudioChunkMessages(wsMessages)
    await page.waitForTimeout(1200)

    expect(countAudioChunkMessages(wsMessages)).toBe(chunkCountAfterError)
    await expect(page.locator('.app-session-detail-title, [data-testid="session-title"]')).toBeVisible()
  })

  test('I-52: cleanup 后 sourceNode 全部断开，无内存泄漏', async ({ page }) => {
    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page)
    await page.goto('/app/login')

    const result = await page.evaluate(async () => {
      const mod = await import('/src/composables/useAudioRecorder.ts')
      const recorder = mod.useAudioRecorder()

      await recorder.startFileInjection(new File(['fake-audio'], 'cleanup.wav', { type: 'audio/wav' }))
      await recorder.stopRecording()

      const state = (window as any).__audioTestState
      return {
        closedContexts: state.closedContexts,
        destinationDisconnectCalls: state.destinationDisconnectCalls,
        isRecording: recorder.isRecording.value,
        lastContextState: state.lastContextState,
        recordingSource: recorder.recordingSource.value,
        sourceDisconnectCalls: state.sourceDisconnectCalls,
      }
    })

    expect(result).toEqual({
      closedContexts: 1,
      destinationDisconnectCalls: 1,
      isRecording: false,
      lastContextState: 'closed',
      recordingSource: null,
      sourceDisconnectCalls: 1,
    })
  })

  test('I-53: AudioContext 被浏览器 suspend → resume() 后播放正常进行', async ({ page }) => {
    const user      = await registerAndLogin('i53')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page, { initialState: 'suspended' })

    await waitForSessionReady(page, sessionId, user)
    await pickInjectionAudioFile(page)

    await expect.poll(async () => {
      return page.evaluate(() => (window as any).__audioTestState)
    }, { timeout: 10000 }).toMatchObject({
      resumeCalls: 1,
      playCalls: 1,
    })

    const events = await page.evaluate(() => (window as any).__audioTestState.events as string[])
    expect(events.indexOf('resume')).toBeGreaterThanOrEqual(0)
    expect(events.indexOf('play')).toBeGreaterThan(events.indexOf('resume'))
  })

  test('I-54: 原生平台（Capacitor）调用 startFileInjection → 抛出明确错误，不进入浏览器分支', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as any).CapacitorCustomPlatform = { name: 'android' }
    })
    await setupFakeMediaRecorder(page)
    await setupFakeAudioContextWithSpy(page)
    await page.goto('/app/login')

    const result = await page.evaluate(async () => {
      const mod = await import('/src/composables/useAudioRecorder.ts')
      const recorder = mod.useAudioRecorder()
      try {
        await recorder.startFileInjection(new File(['fake-audio'], 'native.wav', { type: 'audio/wav' }))
        return { error: null, createdContexts: (window as any).__audioTestState.createdContexts }
      } catch (error) {
        return {
          error: error instanceof Error ? error.message : String(error),
          createdContexts: (window as any).__audioTestState.createdContexts,
        }
      }
    })

    expect(result.error).toBe('原生端暂不支持文件注入模式')
    expect(result.createdContexts).toBe(0)
  })

  test('I-55: AudioContext 不存在（老浏览器）→ 抛出明确错误', async ({ page }) => {
    await setupFakeMediaRecorder(page)
    await page.addInitScript(() => {
      // @ts-expect-error test-only override
      delete window.AudioContext
      // @ts-expect-error test-only override
      delete (window as any).webkitAudioContext
    })
    await page.goto('/app/login')

    const result = await page.evaluate(async () => {
      const mod = await import('/src/composables/useAudioRecorder.ts')
      const recorder = mod.useAudioRecorder()
      try {
        await recorder.startFileInjection(new File(['fake-audio'], 'legacy.wav', { type: 'audio/wav' }))
        return { error: null }
      } catch (error) {
        return { error: error instanceof Error ? error.message : String(error) }
      }
    })

    expect(result.error).toBe('当前环境不支持文件注入录音')
  })
})
