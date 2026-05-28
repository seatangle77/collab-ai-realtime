import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

interface TestUser {
  userId: string
  name: string
  accessToken: string
}

const MOON_ITEM_LABELS = [
  '两罐 100 磅氧气',
  '5 加仑饮用水',
  '星象图（月面星座）',
  '食物浓缩包',
  '太阳能调频收发器',
  '50 英尺尼龙绳',
  '急救箱（含注射针）',
  '降落伞丝绸',
  '救生筏',
  '信号弹',
  '两把 .45 口径手枪',
  '一箱脱水奶粉',
  '便携式加热装置',
  '磁罗盘',
  '一盒火柴',
]

const MOON_ITEM_KEYS = [
  'oxygen_tanks',
  'water_5_gallons',
  'stellar_map',
  'food_concentrate',
  'solar_fm_transceiver',
  'nylon_rope_50ft',
  'first_aid_kit',
  'parachute_silk',
  'life_raft',
  'signal_flares',
  'pistols_45_caliber',
  'dehydrated_milk',
  'portable_heater',
  'magnetic_compass',
  'matches',
]

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts = Date.now()
  const email = `task-score-ui-${label}-${ts}@example.com`
  const password = '1234'
  const name = `TS ${label} ${ts}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!regRes.ok) throw new Error(`register failed: ${await regRes.text()}`)
  const user = await regRes.json()

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error(`login failed: ${await loginRes.text()}`)
  const loginData = await loginRes.json()

  return { userId: user.id, name, accessToken: loginData.access_token }
}

async function createThreeMemberGroup(): Promise<{ groupId: string; groupName: string; members: TestUser[] }> {
  const leader = await registerAndLogin('leader')
  const member1 = await registerAndLogin('member1')
  const member2 = await registerAndLogin('member2')
  const groupName = `任务分数E2E-${Date.now()}`

  const groupRes = await fetch(`${API_BASE}/api/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${leader.accessToken}` },
    body: JSON.stringify({ name: groupName }),
  })
  if (!groupRes.ok) throw new Error(`create group failed: ${await groupRes.text()}`)
  const groupData = await groupRes.json()
  const groupId = groupData.group.id as string

  for (const member of [member1, member2]) {
    const joinRes = await fetch(`${API_BASE}/api/groups/${groupId}/join`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${member.accessToken}` },
    })
    if (!joinRes.ok) throw new Error(`join group failed: ${await joinRes.text()}`)
  }

  return { groupId, groupName, members: [leader, member1, member2] }
}

async function loginAsAdmin(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
}

async function seedTaskScoreEntry(groupId: string, members: TestUser[]): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/task-score-entries/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({
      group_id: groupId,
      task_id: 'moon_survival',
      answers: {
        individual: members.map((member) => ({
          participant_id: member.userId,
          participant_name: member.name,
          ordered_items: MOON_ITEM_KEYS,
        })),
        group_final: {
          ordered_items: MOON_ITEM_KEYS,
        },
      },
    }),
  })
  if (!res.ok) throw new Error(`seed task score failed: ${res.status} ${await res.text()}`)
}

async function chooseElementOption(
  page: import('@playwright/test').Page,
  selectTestId: string,
  optionName: string,
) {
  const select = page.getByTestId(selectTestId)
  await expect(select).toBeVisible()
  await select.click()
  await page.locator('.el-select-dropdown__item:visible').first().waitFor()
  await page.evaluate((name) => {
    const isVisible = (el: Element) => {
      const style = window.getComputedStyle(el)
      const rect = el.getBoundingClientRect()
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
    }
    const dropdowns = Array.from(document.querySelectorAll('.el-select-dropdown')).filter(isVisible)
    const dropdown = dropdowns[dropdowns.length - 1]
    if (!dropdown) throw new Error(`没有找到可见下拉层: ${name}`)

    const options = Array.from(dropdown.querySelectorAll<HTMLElement>('.el-select-dropdown__item'))
    const option = options.find((el) => {
      const text = (el.textContent || '').trim()
      return text.includes(name) && !el.classList.contains('is-disabled')
    })
    if (!option) {
      throw new Error(`没有找到可选项: ${name}`)
    }
    option.click()
  }, optionName)
  await expect(select).toContainText(optionName)
}

test.describe('Admin 任务分数录入', () => {
  test('保存录入后刷新页面可自动回填，并显示计算结果', async ({ page }) => {
    const { groupId, groupName, members } = await createThreeMemberGroup()
    await seedTaskScoreEntry(groupId, members)
    await loginAsAdmin(page)
    await page.goto('/admin/task-score-analysis')
    await expect(page.getByRole('heading', { name: '任务分数' })).toBeVisible()

    await chooseElementOption(page, 'task-score-group-select', groupName)
    await expect(page.getByTestId(`task-score-item-select-${members[0].userId}-1`)).toContainText(MOON_ITEM_LABELS[0])
    await expect(page.getByTestId(`task-score-item-select-${members[0].userId}-2`)).toContainText(MOON_ITEM_LABELS[1])
    await expect(page.getByTestId('task-score-item-select-group_final-1')).toContainText(MOON_ITEM_LABELS[0])
    await expect(page.getByText('GS 小组最终分')).toBeVisible()
    await expect(page.getByText('强协同值 Best IS - GS')).toBeVisible()

    await page.getByTestId('task-score-save-button').click()
    await expect(page.getByText('任务分数录入已保存')).toBeVisible()

    await page.reload()
    await chooseElementOption(page, 'task-score-group-select', groupName)
    await expect(page.getByText('GS 小组最终分')).toBeVisible()
    await expect(page.getByTestId(`task-score-item-select-${members[0].userId}-1`)).toContainText('两罐 100 磅氧气')
  })
})
