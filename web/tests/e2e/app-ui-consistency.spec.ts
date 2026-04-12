import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

interface MockUser {
  id: string
  name: string
  email: string
}

interface MockGroup {
  id: string
  name: string
}

const user: MockUser = {
  id: 'user-step6',
  name: 'Step6 User',
  email: 'step6@example.com',
}

const group: MockGroup = {
  id: 'group-step6',
  name: 'Step6 群组',
}

const voiceProfile = {
  id: 'vp-step6',
  user_id: user.id,
  sample_audio_urls: ['https://example.com/a.wav'],
  created_at: '2026-01-01T08:00:00.000Z',
  voice_embedding: [0.1, 0.2],
  embedding_status: 'ready',
  embedding_updated_at: '2026-01-02T08:00:00.000Z',
}

const groupSummary = {
  id: group.id,
  name: group.name,
  created_at: '2026-01-01T08:00:00.000Z',
  is_active: true,
  member_count: 2,
  my_role: 'leader',
}

const groupDetail = {
  group: {
    id: group.id,
    name: group.name,
    created_at: '2026-01-01T08:00:00.000Z',
    is_active: true,
  },
  member_count: 2,
  members: [
    { user_id: user.id, user_name: user.name, role: 'leader', status: 'active' },
    { user_id: 'user-b', user_name: '成员B', role: 'member', status: 'active' },
  ],
  my_role: 'leader',
}

const sessionList = [
  {
    id: 'session-step6',
    group_id: group.id,
    created_at: '2026-01-01T08:00:00.000Z',
    last_updated: '2026-01-01T08:30:00.000Z',
    session_title: 'Step6 会话',
    status: 'not_started',
    created_by: user.id,
  },
]

function rgb(value: string): string {
  return value.replace(/\s+/g, '')
}

async function seedAuthedApp(page: Page) {
  await page.addInitScript(
    ({ seededUser, seededGroup }) => {
      localStorage.setItem('app_access_token', 'mock-token')
      localStorage.setItem('app_user', JSON.stringify(seededUser))
      localStorage.setItem('app_current_group', JSON.stringify(seededGroup))
    },
    { seededUser: user, seededGroup: group },
  )
}

async function mockCommonApis(page: Page) {
  await page.route('**/api/groups/my', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([groupSummary]) })
  })

  await page.route(`**/api/groups/${group.id}`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(groupDetail) })
  })

  await page.route('**/api/groups/discover**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.route(`**/api/groups/${group.id}/sessions**`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sessionList) })
  })

  await page.route('**/api/voice-profile/me', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(voiceProfile) })
  })

  await page.route('**/api/sessions/session-step6/transcripts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          transcript_id: 'tx-1',
          group_id: group.id,
          session_id: 'session-step6',
          speaker: user.id,
          speaker_name: user.name,
          text: '先看设计 token。',
          start: '2026-01-01T08:00:01.000Z',
          end: '2026-01-01T08:00:04.000Z',
          created_at: '2026-01-01T08:00:04.000Z',
        },
      ]),
    })
  })

  await page.route('**/api/sessions/session-step6/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ content: '这是一个用于样式验收的讨论摘要。', version: 3 }),
    })
  })

  await page.route('**/api/sessions/session-step6/push-logs', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'push-style',
          session_id: 'session-step6',
          target_user_id: user.id,
          push_content: '请重点关注 AI 建议色是否统一。',
          push_channel: 'web',
          delivery_status: 'delivered',
          triggered_at: '2026-01-01T08:00:05.000Z',
          delivered_at: null,
        },
      ]),
    })
  })

  await page.route('**/api/sessions/session-step6/info-gap/buttons', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 'ig-style', keyword: 'token', skw_score: 0.2 }]),
    })
  })
}

async function mockFakeWs(page: Page) {
  await page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      constructor() {
        ;(window as any).__lastWs = this
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
          this.onmessage?.(
            new MessageEvent('message', { data: JSON.stringify({ type: 'connected', data: {} }) }),
          )
        }, 0)
      }
      send() {}
      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }
      addEventListener() {}
      removeEventListener() {}
      dispatchEvent() {
        return true
      }
    }
    ;(window as any).WebSocket = MockWebSocket
  })
}

test.describe('Step 6 - UI Consistency', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthedApp(page)
    await mockCommonApis(page)
    await mockFakeWs(page)
  })

  test('titles and page widths use the shared tokens', async ({ page }) => {
    await page.goto('/app')
    await expect(page.locator('.app-home-title')).toBeVisible()
    expect(await page.locator('.app-home-title').evaluate((el) => getComputedStyle(el).fontSize)).toBe('22px')
    expect(await page.locator('.app-home-stack').evaluate((el) => getComputedStyle(el).maxWidth)).toBe('720px')

    await page.goto('/app/sessions')
    await expect(page.locator('.app-sessions-title')).toBeVisible()
    expect(await page.locator('.app-sessions-title').evaluate((el) => getComputedStyle(el).fontSize)).toBe('22px')
    expect(await page.locator('.app-sessions').evaluate((el) => getComputedStyle(el).maxWidth)).toBe('840px')

    await page.goto('/app/groups')
    await expect(page.locator('.app-groups-title')).toBeVisible()
    expect(await page.locator('.app-groups-title').evaluate((el) => getComputedStyle(el).fontSize)).toBe('22px')
    expect(await page.locator('.app-groups').evaluate((el) => getComputedStyle(el).maxWidth)).toBe('840px')

    await page.goto('/app/voice-profile')
    await expect(page.locator('.app-voice-profile-title')).toBeVisible()
    expect(await page.locator('.app-voice-profile-title').evaluate((el) => getComputedStyle(el).fontSize)).toBe('22px')
    expect(await page.locator('.app-voice-profile-card').evaluate((el) => getComputedStyle(el).maxWidth)).toBe('720px')
  })

  test('primary actions and utility buttons use pill corners', async ({ page }) => {
    await page.goto('/app/sessions')
    expect(await page.locator('.app-sessions-primary-btn').evaluate((el) => getComputedStyle(el).borderRadius)).toBe('999px')
    expect(await page.locator('.app-sessions-more-btn').first().evaluate((el) => getComputedStyle(el).borderRadius)).toBe('999px')

    await page.goto('/app/sessions/session-step6')
    await expect(page.locator('.app-session-detail-primary-btn')).toBeVisible()
    expect(await page.locator('.app-session-detail-primary-btn').evaluate((el) => getComputedStyle(el).borderRadius)).toBe('999px')
    expect(await page.locator('.app-session-detail-more-btn').evaluate((el) => getComputedStyle(el).borderRadius)).toBe('999px')

    await page.goto('/app/groups')
    expect(await page.locator('.app-groups-group').evaluate((el) => getComputedStyle(el).borderRadius)).toBe('999px')
  })

  test('AI suggestion card uses the semantic AI colors', async ({ page }) => {
    await page.goto('/app/sessions/session-step6')
    const aiCard = page.locator('.app-session-detail-ai-card')
    await expect(aiCard).toBeVisible()

    const styles = await aiCard.evaluate((el) => {
      const css = getComputedStyle(el)
      return {
        backgroundColor: css.backgroundColor,
        borderLeftColor: css.borderLeftColor,
        borderLeftWidth: css.borderLeftWidth,
      }
    })

    expect(rgb(styles.backgroundColor)).toBe(rgb('rgb(255, 251, 235)'))
    expect(rgb(styles.borderLeftColor)).toBe(rgb('rgb(245, 158, 11)'))
    expect(styles.borderLeftWidth).toBe('3px')
  })

  test('source audit blocks legacy hard-coded AI and leader colors in app pages', async () => {
    const appDir = path.resolve(process.cwd(), 'src', 'views', 'app')
    const targets = [
      path.join(appDir, 'AppGroups.vue'),
      path.join(appDir, 'AppSessionDetailPage.vue'),
      path.join(appDir, 'AppSessions.vue'),
      path.join(appDir, 'AppHome.vue'),
      path.join(appDir, 'AppVoiceProfile.vue'),
    ]

    const forbiddenColors = ['#fef3c7', '#b45309', '#fff7ed', '#fdba74']

    for (const file of targets) {
      const content = await fs.readFile(file, 'utf8')
      for (const color of forbiddenColors) {
        expect.soft(
          content.toLowerCase().includes(color),
          `${path.basename(file)} should not contain hard-coded color ${color}`,
        ).toBeFalsy()
      }
    }
  })
})
