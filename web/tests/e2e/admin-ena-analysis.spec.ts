import { test, expect, type Page } from '@playwright/test'
import { loginAsAdmin } from './admin-helpers'

// ─────────────────────────────────────────────────────────────────
// Mock data helpers
// ─────────────────────────────────────────────────────────────────

function mockGroups() {
  return {
    items: [
      { id: 'g1', name: '第一组', condition: 'no_assistance' },
      { id: 'g2', name: '第二组', condition: 'no_assistance' },
      { id: 'g3', name: '第三组', condition: 'glasses' },
      { id: 'g4', name: '第四组', condition: 'glasses' },
      { id: 'g5', name: '第五组', condition: 'app_notification' },
    ],
    meta: { total: 5, page: 1, page_size: 200 },
  }
}

function mockEnaResult(mode: 'two_conditions' | 'three_conditions' = 'two_conditions') {
  const conditions = mode === 'two_conditions'
    ? ['no_assistance', 'glasses']
    : ['no_assistance', 'glasses', 'app_notification']

  return {
    mode,
    conditions,
    total_sessions: mode === 'two_conditions' ? 4 : 6,
    sessions_by_condition: mode === 'two_conditions'
      ? { no_assistance: 2, glasses: 2 }
      : { no_assistance: 2, glasses: 2, app_notification: 2 },
    observations: [
      { session_id: 's1', group_id: 'g1', condition: 'no_assistance', ex_in_strength: 0.25, in_re_strength: 0.10, higher_order_strength: 0.05, total_windows: 8 },
      { session_id: 's2', group_id: 'g2', condition: 'no_assistance', ex_in_strength: 0.30, in_re_strength: 0.15, higher_order_strength: 0.08, total_windows: 10 },
      { session_id: 's3', group_id: 'g3', condition: 'glasses',       ex_in_strength: 0.55, in_re_strength: 0.35, higher_order_strength: 0.20, total_windows: 9 },
      { session_id: 's4', group_id: 'g4', condition: 'glasses',       ex_in_strength: 0.60, in_re_strength: 0.40, higher_order_strength: 0.25, total_windows: 11 },
    ],
    metrics: [
      {
        metric: 'ex_in_strength',
        label: 'EX-IN 连接强度（探索→整合）',
        conditions: [
          { condition: 'no_assistance', n: 2, mean: 0.275, sd: 0.035, median: 0.275, min: 0.25, max: 0.30 },
          { condition: 'glasses',       n: 2, mean: 0.575, sd: 0.035, median: 0.575, min: 0.55, max: 0.60 },
        ],
      },
      {
        metric: 'in_re_strength',
        label: 'IN-RE 连接强度（整合→解决）',
        conditions: [
          { condition: 'no_assistance', n: 2, mean: 0.125, sd: 0.035, median: 0.125, min: 0.10, max: 0.15 },
          { condition: 'glasses',       n: 2, mean: 0.375, sd: 0.035, median: 0.375, min: 0.35, max: 0.40 },
        ],
      },
      {
        metric: 'higher_order_strength',
        label: '高阶认知连接强度（EX+IN+RE 共现）',
        conditions: [
          { condition: 'no_assistance', n: 2, mean: 0.065, sd: 0.021, median: 0.065, min: 0.05, max: 0.08 },
          { condition: 'glasses',       n: 2, mean: 0.225, sd: 0.035, median: 0.225, min: 0.20, max: 0.25 },
        ],
      },
    ],
    normality: [
      { metric: 'ex_in_strength',        label: 'EX-IN 连接强度（探索→整合）',         condition: 'no_assistance', n: 2, test: 'shapiro_wilk', statistic: null, p_value: null, is_normal: null, alpha: 0.05, status: 'insufficient_n', note: 'Shapiro-Wilk 至少需要 3 个样本' },
      { metric: 'ex_in_strength',        label: 'EX-IN 连接强度（探索→整合）',         condition: 'glasses',       n: 2, test: 'shapiro_wilk', statistic: null, p_value: null, is_normal: null, alpha: 0.05, status: 'insufficient_n', note: 'Shapiro-Wilk 至少需要 3 个样本' },
      { metric: 'in_re_strength',        label: 'IN-RE 连接强度（整合→解决）',         condition: 'no_assistance', n: 2, test: 'shapiro_wilk', statistic: null, p_value: null, is_normal: null, alpha: 0.05, status: 'insufficient_n', note: 'Shapiro-Wilk 至少需要 3 个样本' },
      { metric: 'in_re_strength',        label: 'IN-RE 连接强度（整合→解决）',         condition: 'glasses',       n: 2, test: 'shapiro_wilk', statistic: null, p_value: null, is_normal: null, alpha: 0.05, status: 'insufficient_n', note: 'Shapiro-Wilk 至少需要 3 个样本' },
      { metric: 'higher_order_strength', label: '高阶认知连接强度（EX+IN+RE 共现）', condition: 'no_assistance', n: 2, test: 'shapiro_wilk', statistic: null, p_value: null, is_normal: null, alpha: 0.05, status: 'insufficient_n', note: 'Shapiro-Wilk 至少需要 3 个样本' },
      { metric: 'higher_order_strength', label: '高阶认知连接强度（EX+IN+RE 共现）', condition: 'glasses',       n: 2, test: 'shapiro_wilk', statistic: null, p_value: null, is_normal: null, alpha: 0.05, status: 'insufficient_n', note: 'Shapiro-Wilk 至少需要 3 个样本' },
    ],
    test_recommendations: [],
    statistical_tests: [
      { metric: 'ex_in_strength',        label: 'EX-IN 连接强度（探索→整合）',         test: 'mann_whitney_u', statistic_name: 'U', statistic: 0.0, p_value: 0.083, effect_size_name: 'rank-biserial r', effect_size: -1.0, status: 'ok', note: 'Mann-Whitney U test（双尾）' },
      { metric: 'in_re_strength',        label: 'IN-RE 连接强度（整合→解决）',         test: 'mann_whitney_u', statistic_name: 'U', statistic: 0.0, p_value: 0.083, effect_size_name: 'rank-biserial r', effect_size: -1.0, status: 'ok', note: 'Mann-Whitney U test（双尾）' },
      { metric: 'higher_order_strength', label: '高阶认知连接强度（EX+IN+RE 共现）', test: 'mann_whitney_u', statistic_name: 'U', statistic: 0.0, p_value: 0.083, effect_size_name: 'rank-biserial r', effect_size: -1.0, status: 'ok', note: 'Mann-Whitney U test（双尾）' },
    ],
    post_hoc_tests: [
      { metric: 'ex_in_strength',        label: 'EX-IN 连接强度（探索→整合）',         method: null, pairs: [], status: 'not_applicable', note: '仅三条件全局检验有意义时才执行事后检验' },
      { metric: 'in_re_strength',        label: 'IN-RE 连接强度（整合→解决）',         method: null, pairs: [], status: 'not_applicable', note: '仅三条件全局检验有意义时才执行事后检验' },
      { metric: 'higher_order_strength', label: '高阶认知连接强度（EX+IN+RE 共现）', method: null, pairs: [], status: 'not_applicable', note: '仅三条件全局检验有意义时才执行事后检验' },
    ],
    networks: [
      {
        condition: 'no_assistance',
        nodes: ['TE', 'EX', 'IN', 'RE'],
        edges: [
          { source: 'EX', target: 'IN', weight: 0.275, weight_diff: null },
          { source: 'IN', target: 'RE', weight: 0.125, weight_diff: null },
          { source: 'TE', target: 'EX', weight: 0.1,   weight_diff: null },
          { source: 'TE', target: 'IN', weight: 0.05,  weight_diff: null },
          { source: 'TE', target: 'RE', weight: 0.02,  weight_diff: null },
          { source: 'EX', target: 'RE', weight: 0.065, weight_diff: null },
        ],
      },
      {
        condition: 'glasses',
        nodes: ['TE', 'EX', 'IN', 'RE'],
        edges: [
          { source: 'EX', target: 'IN', weight: 0.575, weight_diff: null },
          { source: 'IN', target: 'RE', weight: 0.375, weight_diff: null },
          { source: 'TE', target: 'EX', weight: 0.15,  weight_diff: null },
          { source: 'TE', target: 'IN', weight: 0.08,  weight_diff: null },
          { source: 'TE', target: 'RE', weight: 0.04,  weight_diff: null },
          { source: 'EX', target: 'RE', weight: 0.225, weight_diff: null },
        ],
      },
    ],
    diff_network: mode === 'two_conditions' ? {
      condition: 'diff',
      nodes: ['TE', 'EX', 'IN', 'RE'],
      edges: [
        { source: 'EX', target: 'IN', weight: 0.575, weight_diff: 0.3  },
        { source: 'IN', target: 'RE', weight: 0.375, weight_diff: 0.25 },
        { source: 'TE', target: 'EX', weight: 0.15,  weight_diff: 0.05 },
        { source: 'TE', target: 'IN', weight: 0.08,  weight_diff: 0.03 },
        { source: 'TE', target: 'RE', weight: 0.04,  weight_diff: 0.02 },
        { source: 'EX', target: 'RE', weight: 0.225, weight_diff: 0.16 },
      ],
    } : null,
  }
}

// ─────────────────────────────────────────────────────────────────
// SampleSelector helper: open dialog → select all → confirm
// ─────────────────────────────────────────────────────────────────

async function selectAllGroupsForCondition(page: Page, conditionIndex: number) {
  // SampleSelector renders one trigger button per condition in order
  const triggers = page.locator('.sample-select-trigger')
  await triggers.nth(conditionIndex).click()
  // Dialog opens; click 全选
  await page.getByRole('button', { name: '全选' }).click()
  // Close dialog
  await page.getByRole('button', { name: '完成' }).click()
  await expect(page.locator('.el-dialog')).toBeHidden()
}

// ─────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────

test.describe.serial('ENA 认知过程网络分析页', () => {
  test('1. 页面渲染：标题、控件、样本选择区正常显示', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.goto('/admin/ena-analysis')
    await expect(page.getByRole('heading', { name: 'ENA 认知过程网络分析' })).toBeVisible()
    await expect(page.getByText('两条件')).toBeVisible()
    await expect(page.getByText('三条件')).toBeVisible()
    await expect(page.getByText('2 分钟窗口')).toBeVisible()
    await expect(page.getByRole('button', { name: '生成分析' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下载 HTML 报告' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '打印 / PDF' })).toBeDisabled()

    // SampleSelector shows condition labels and trigger buttons
    await expect(page.getByText('无辅助').first()).toBeVisible()
    await expect(page.getByText('智能眼镜').first()).toBeVisible()
    await expect(page.locator('.sample-select-trigger').first()).toBeVisible()
  })

  test('2. 打开样本选择对话框，可以看到小组名称', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.goto('/admin/ena-analysis')
    // Open first condition dialog
    await page.locator('.sample-select-trigger').first().click()
    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.getByText('第一组')).toBeVisible()
    await expect(page.getByText('第二组')).toBeVisible()
    await page.getByRole('button', { name: '完成' }).click()
  })

  test('3. 未选小组时点生成分析，显示警告', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.goto('/admin/ena-analysis')
    await page.getByRole('button', { name: '生成分析' }).click()
    await expect(page.getByText(/请为.*选择要纳入分析的小组/)).toBeVisible()
  })

  test('4. 选择小组后生成分析，显示描述统计和正态性表', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult()) })
        return
      }
      await route.fallback()
    })

    await page.goto('/admin/ena-analysis')
    await selectAllGroupsForCondition(page, 0)  // no_assistance
    await selectAllGroupsForCondition(page, 1)  // glasses
    await page.getByRole('button', { name: '生成分析' }).click()

    await expect(page.getByText('描述性统计')).toBeVisible()
    await expect(page.getByText('EX-IN 连接强度（探索→整合）').first()).toBeVisible()
    await expect(page.getByText('IN-RE 连接强度（整合→解决）').first()).toBeVisible()
    await expect(page.getByText('高阶认知连接强度（EX+IN+RE 共现）').first()).toBeVisible()

    await expect(page.getByText('正态性检查')).toBeVisible()
    await expect(page.getByText('样本不足').first()).toBeVisible()
  })

  test('5. 推断统计表显示检验结果', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult()) })
        return
      }
      await route.fallback()
    })

    await page.goto('/admin/ena-analysis')
    await selectAllGroupsForCondition(page, 0)
    await selectAllGroupsForCondition(page, 1)
    await page.getByRole('button', { name: '生成分析' }).click()

    await expect(page.getByText('推断统计结果')).toBeVisible()
    await expect(page.getByText('Mann-Whitney U').first()).toBeVisible()
    await expect(page.getByText('rank-biserial r').first()).toBeVisible()
  })

  test('6. 网络图渲染：两条件网络图 + 差异图', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult()) })
        return
      }
      await route.fallback()
    })

    await page.goto('/admin/ena-analysis')
    await selectAllGroupsForCondition(page, 0)
    await selectAllGroupsForCondition(page, 1)
    await page.getByRole('button', { name: '生成分析' }).click()

    await expect(page.getByText('ENA 认知过程网络图')).toBeVisible()
    await expect(page.locator('[data-testid="network-no_assistance"]')).toBeVisible()
    await expect(page.locator('[data-testid="network-glasses"]')).toBeVisible()
    await expect(page.locator('[data-testid="network-diff"]')).toBeVisible()
    await expect(page.getByText('差异图（条件B − 条件A）')).toBeVisible()
    await expect(page.getByText('蓝色：条件B 连接更强')).toBeVisible()
    await expect(page.getByText('红色：条件A 连接更强')).toBeVisible()
  })

  test('7. 三条件模式：显示事后检验，不显示差异图', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult('three_conditions')) })
        return
      }
      await route.fallback()
    })

    await page.goto('/admin/ena-analysis')
    await page.getByText('三条件').click()
    await selectAllGroupsForCondition(page, 0)
    await selectAllGroupsForCondition(page, 1)
    await selectAllGroupsForCondition(page, 2)
    await page.getByRole('button', { name: '生成分析' }).click()

    await expect(page.getByText('事后检验（Post-hoc）')).toBeVisible()
    await expect(page.locator('[data-testid="network-diff"]')).toHaveCount(0)
  })

  test('8. 会话概览数字正确显示', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult()) })
        return
      }
      await route.fallback()
    })

    await page.goto('/admin/ena-analysis')
    await selectAllGroupsForCondition(page, 0)
    await selectAllGroupsForCondition(page, 1)
    await page.getByRole('button', { name: '生成分析' }).click()

    await expect(page.getByText('纳入会话数')).toBeVisible()
    await expect(page.locator('.summary-card').first()).toContainText('4')
  })

  test('9. API 失败时显示错误提示，已有结果不被清除', async ({ page }) => {
    await loginAsAdmin(page)
    let callCount = 0

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() !== 'POST') { await route.fallback(); return }
      callCount++
      if (callCount === 1) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult()) })
      } else {
        await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '服务器错误' }) })
      }
    })

    await page.goto('/admin/ena-analysis')
    await selectAllGroupsForCondition(page, 0)
    await selectAllGroupsForCondition(page, 1)

    await page.getByRole('button', { name: '生成分析' }).click()
    await expect(page.getByText('ENA 认知过程网络图')).toBeVisible()

    await page.getByRole('button', { name: '生成分析' }).click()
    await expect(page.getByText(/生成 ENA 分析失败|服务器错误/)).toBeVisible()
    await expect(page.getByText('ENA 认知过程网络图')).toBeVisible()
  })

  test('10. 下载 HTML 报告：分析前禁用，分析后可下载', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定')

    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.route('**/api/admin/ena-analysis/**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockEnaResult()) })
        return
      }
      await route.fallback()
    })

    await page.goto('/admin/ena-analysis')
    await expect(page.getByRole('button', { name: '下载 HTML 报告' })).toBeDisabled()

    await selectAllGroupsForCondition(page, 0)
    await selectAllGroupsForCondition(page, 1)
    await page.getByRole('button', { name: '生成分析' }).click()
    await expect(page.getByText('ENA 认知过程网络图')).toBeVisible()

    await expect(page.getByRole('button', { name: '下载 HTML 报告' })).toBeEnabled()

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: '下载 HTML 报告' }).click(),
    ])
    expect(download.suggestedFilename()).toMatch(/^ena-analysis-report-.*\.html$/)
  })

  test('11. 导航菜单包含 ENA 入口', async ({ page }) => {
    await loginAsAdmin(page)

    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockGroups()) })
    })

    await page.goto('/admin/ena-analysis')
    await expect(page.getByRole('menuitem', { name: 'ENA 认知过程网络分析' })).toBeVisible()
  })
})
