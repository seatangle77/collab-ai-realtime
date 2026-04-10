import { test, expect } from '@playwright/test'
import {
  loginAsAdminAndGoToPage,
} from './admin-helpers'

type DiscussionRules = {
  silence_threshold_minutes: number
  speaking_ratio_min: number
  speaking_ratio_max: number
  cosine_similarity_threshold: number
  min_session_duration_minutes: number
  push_interval_minutes: number
  max_push_per_member: number
  analysis_enabled: boolean
  updated_at: string
  personal_stagnation_ratio: number | null
  group_silence_threshold_s: number | null
  srep_threshold: number | null
  ttr_threshold: number | null
  arg_density_threshold: number | null
  info_gain_threshold: number | null
  skw_threshold_low: number | null
  skw_threshold_high: number | null
  same_state_cooldown_s: number | null
  cross_state_cooldown_s: number | null
}

let originalRules: DiscussionRules
let currentRules: DiscussionRules

const BASE_RULES: DiscussionRules = {
  silence_threshold_minutes: 5,
  speaking_ratio_min: 0.1,
  speaking_ratio_max: 0.6,
  cosine_similarity_threshold: 0.35,
  min_session_duration_minutes: 8,
  push_interval_minutes: 15,
  max_push_per_member: 3,
  analysis_enabled: true,
  updated_at: '2026-04-10T10:00:00Z',
  personal_stagnation_ratio: 0.2,
  group_silence_threshold_s: 30,
  srep_threshold: 0.3,
  ttr_threshold: 0.4,
  arg_density_threshold: 0.2,
  info_gain_threshold: 0.25,
  skw_threshold_low: 0.2,
  skw_threshold_high: 0.7,
  same_state_cooldown_s: 60,
  cross_state_cooldown_s: 120,
}

function rulesEndpoint() {
  return '**/api/admin/discussion-rules/'
}

function rulesPath() {
  return '/admin/discussion-rules'
}

function getNumberInput(page: import('@playwright/test').Page, label: string) {
  return page.locator('.el-form-item').filter({ hasText: label }).locator('input').first()
}

async function setNumberInput(
  page: import('@playwright/test').Page,
  label: string,
  value: string,
) {
  const input = getNumberInput(page, label)
  await input.click()
  await input.fill('')
  await input.fill(value)
}

async function expectNumericValue(
  page: import('@playwright/test').Page,
  label: string,
  expected: number,
) {
  await expect.poll(async () => {
    const raw = await getNumberInput(page, label).inputValue()
    return Number(raw)
  }).toBe(expected)
}

async function expectSwitchChecked(
  page: import('@playwright/test').Page,
  expected: boolean,
) {
  const input = page.locator('.analysis-switch-row input[type="checkbox"]').first()
  await expect.poll(async () => await input.isChecked()).toBe(expected)
}

test.describe.serial('Admin 讨论规则配置页', () => {
  test.beforeEach(async ({ page }) => {
    originalRules = { ...BASE_RULES }
    currentRules = { ...BASE_RULES }

    await page.route(rulesEndpoint(), async (route) => {
      const method = route.request().method()

      if (method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(currentRules),
        })
        return
      }

      if (method === 'PUT') {
        const payload = route.request().postDataJSON() as Partial<DiscussionRules>
        currentRules = {
          ...currentRules,
          ...payload,
          updated_at: '2026-04-10T10:30:00Z',
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(currentRules),
        })
        return
      }

      await route.fallback()
    })

    await loginAsAdminAndGoToPage(page, rulesPath(), '讨论规则配置')
  })

  test('1. 页面加载并展示当前规则值', async ({ page }) => {
    await expect(page.getByText('AI 分析开关')).toBeVisible()
    await expectNumericValue(page, '静默阈值（分钟）', originalRules.silence_threshold_minutes)
    await expectNumericValue(page, '发言比例最小值', originalRules.speaking_ratio_min)
    await expectNumericValue(page, '发言比例最大值', originalRules.speaking_ratio_max)
    await expect(page.getByText(/最后更新时间：/)).toBeVisible()
  })

  test('2. 发言比例最小值大于最大值时前端拦截且不发 PUT', async ({ page }) => {
    let putCount = 0
    page.on('request', (request) => {
      if (request.method() === 'PUT' && request.url().includes(rulesEndpoint())) {
        putCount += 1
      }
    })

    await setNumberInput(page, '发言比例最小值', '0.90')
    await setNumberInput(page, '发言比例最大值', '0.20')
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('发言比例最小值必须小于最大值')).toBeVisible()
    await page.waitForTimeout(300)
    expect(putCount).toBe(0)
  })

  test('3. 发言比例超范围时不会提交保存', async ({ page }) => {
    let putCount = 0
    page.on('request', (request) => {
      if (request.method() === 'PUT' && request.url().includes('/api/admin/discussion-rules/')) {
        putCount += 1
      }
    })

    await setNumberInput(page, '发言比例最小值', '1.20')
    await page.getByRole('button', { name: '保存' }).click()
    await page.waitForTimeout(300)
    expect(putCount).toBe(0)
  })

  test('4. SKW 低阈值不小于高阈值时前端拦截且不发 PUT', async ({ page }) => {
    let putCount = 0
    page.on('request', (request) => {
      if (request.method() === 'PUT' && request.url().includes(rulesEndpoint())) {
        putCount += 1
      }
    })

    await setNumberInput(page, 'SKW 低阈值', '0.80')
    await setNumberInput(page, 'SKW 高阈值', '0.20')
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('SKW 低阈值必须小于高阈值')).toBeVisible()
    await page.waitForTimeout(300)
    expect(putCount).toBe(0)
  })

  test('5. 正常保存后页面回填更新值，并在刷新后保持持久化', async ({ page }) => {
    const silenceValue = String(originalRules.silence_threshold_minutes + 1)
    const pushIntervalValue = String(originalRules.push_interval_minutes + 1)
    const maxPushValue = String(originalRules.max_push_per_member + 1)
    const expectedSwitchValue = !originalRules.analysis_enabled

    const switchEl = page.locator('.analysis-switch-row .el-switch')
    await expectSwitchChecked(page, originalRules.analysis_enabled)

    await setNumberInput(page, '静默阈值（分钟）', silenceValue)
    await setNumberInput(page, '推送间隔（分钟）', pushIntervalValue)
    await setNumberInput(page, '每人最大推送次数', maxPushValue)
    await switchEl.click()
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page.getByText('保存成功')).toBeVisible()
    await expectNumericValue(page, '静默阈值（分钟）', Number(silenceValue))
    await expectNumericValue(page, '推送间隔（分钟）', Number(pushIntervalValue))
    await expectNumericValue(page, '每人最大推送次数', Number(maxPushValue))
    await expectSwitchChecked(page, expectedSwitchValue)

    await page.reload()
    await expect(page.getByRole('heading', { name: '讨论规则配置' })).toBeVisible()
    await expectNumericValue(page, '静默阈值（分钟）', Number(silenceValue))
    await expectNumericValue(page, '推送间隔（分钟）', Number(pushIntervalValue))
    await expectNumericValue(page, '每人最大推送次数', Number(maxPushValue))
    await expectSwitchChecked(page, expectedSwitchValue)
  })
})
