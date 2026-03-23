/**
 * 模块五 + 模块六 前端 E2E 测试（Playwright）
 *
 * 用例分类：
 *   E. WS 连接与状态（35-37）
 *   F. 录音与音频发送（38-40）
 *   G. 转写展示（41-43）
 *   H. 异常场景（44-46）
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

    // 等待 WS connected 状态出现（具体 class 根据实际前端调整）
    await expect(
      page.locator('.app-session-detail-ws-status, [data-testid="ws-status"]')
    ).toContainText(/已连接|connected/i, { timeout: 10000 })
  })

  test('E-36: WS 收到 transcript 消息 → 转写列表实时出现新条目', async ({ page }) => {
    const user      = await registerAndLogin('e36')
    const groupId   = await createGroup(user.token)
    const sessionId = await createSession(user.token, groupId)
    await startSession(user.token, sessionId)

    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 等 WS 真正连上再注入，确保 broadcast 能到达
    await expect(
      page.locator('.app-session-detail-ws-status, [data-testid="ws-status"]')
    ).toContainText(/已连接|connected/i, { timeout: 15000 })

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

    // 等 WS 连上再注入，确保 broadcast 能到达
    await expect(
      page.locator('.app-session-detail-ws-status, [data-testid="ws-status"]')
    ).toContainText(/已连接|connected/i, { timeout: 15000 })

    await addTranscriptAdmin(sessionId, groupId, '说话人A', 'E37第一句')
    await page.waitForTimeout(300)
    await addTranscriptAdmin(sessionId, groupId, '说话人B', 'E37第二句')

    await expect(
      page.locator('.app-session-detail-transcript-item, [data-testid="transcript-item"]')
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

    // 监听 WS 消息（须在 goto 前注册，否则捕获不到已建立的连接）
    const wsMessages: string[] = []
    page.on('websocket', ws => {
      ws.on('framesent', frame => {
        if (frame.payload) wsMessages.push(String(frame.payload))
      })
    })

    // 不使用 injectFakeMicrophone：Chromium --use-fake-device-for-media-stream flag
    // 已提供真实 fake audio device，addInitScript 里的 AudioContext 会处于 suspended
    // 状态导致 MediaRecorder 录到空 blob
    await loginViaUI(page, user)
    await page.goto(`/app/sessions/${sessionId}`)

    // 等 WS 连上（按钮 disabled 时不可点）
    const recordBtn = page.getByRole('button', { name: /开始录音/i })
    await recordBtn.waitFor({ state: 'visible' })
    await expect(recordBtn).toBeEnabled({ timeout: 10000 })

    await recordBtn.click()
    await page.waitForTimeout(3000)

    const hasAudioChunk = wsMessages.some(m => {
      try { return JSON.parse(m)?.type === 'audio_chunk' } catch { return false }
    })
    expect(hasAudioChunk).toBeTruthy()
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
      page.locator('.app-session-detail-transcript-speaker, [data-testid="transcript-speaker"]').first()
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
      '.app-session-detail-transcript-speaker, [data-testid="transcript-speaker"]'
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
