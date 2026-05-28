import { test, expect } from '@playwright/test'

const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

// ── mock 数据 ─────────────────────────────────────────────────────────────────

const MOCK_GROUPS = {
  items: [
    { id: 'g-na-1', name: '无辅助小组 A', condition: 'no_assistance' },
    { id: 'g-na-2', name: '无辅助小组 B', condition: 'no_assistance' },
    { id: 'g-gl-1', name: '智能眼镜小组 A', condition: 'glasses' },
    { id: 'g-gl-2', name: '智能眼镜小组 B', condition: 'glasses' },
    { id: 'g-app-1', name: 'APP 通知小组 A', condition: 'app_notification' },
  ],
  meta: { total: 5, page: 1, page_size: 200 },
}

function makeMockReport(mode: 'two_conditions' | 'three_conditions') {
  const conditions = mode === 'two_conditions'
    ? ['no_assistance', 'glasses']
    : ['no_assistance', 'glasses', 'app_notification']

  const metrics = [
    'te_ratio', 'ex_ratio', 'in_ratio', 're_ratio', 'higher_order_ratio', 'weighted_score',
  ].map((metric) => ({
    metric,
    label: {
      te_ratio: 'Triggering Event 比例',
      ex_ratio: 'Exploration 比例',
      in_ratio: 'Integration 比例',
      re_ratio: 'Resolution 比例',
      higher_order_ratio: '高阶认知参与比例 (IN+RE)',
      weighted_score: '认知参与加权得分',
    }[metric],
    conditions: conditions.map((c) => ({
      condition: c, n: 2, mean: 0.25, sd: 0.05, median: 0.25, min: 0.20, max: 0.30,
    })),
  }))

  const normality = metrics.flatMap((m) =>
    conditions.map((c) => ({
      metric: m.metric, label: m.label, condition: c, n: 2,
      test: 'shapiro_wilk', statistic: 0.95, p_value: 0.08,
      is_normal: true, alpha: 0.05, status: 'ok', note: 'p >= 0.05 时按近似正态处理',
    })),
  )

  const statistical_tests = metrics.map((m) => ({
    metric: m.metric, label: m.label,
    test: mode === 'two_conditions' ? 'independent_samples_t_test' : 'one_way_anova',
    statistic_name: mode === 'two_conditions' ? 't' : 'F',
    statistic: 1.23, p_value: 0.24,
    effect_size_name: mode === 'two_conditions' ? "Cohen's d" : 'eta squared',
    effect_size: 0.18,
    status: 'ok', note: '已计算',
  }))

  const post_hoc_tests = metrics.map((m) => ({
    metric: m.metric, label: m.label,
    method: mode === 'three_conditions' ? 'tukey_hsd' : null,
    pairs: mode === 'three_conditions' ? [
      { condition_a: 'no_assistance', condition_b: 'glasses', mean_diff: 0.05, p_value_adjusted: 0.30, significant: false, alpha: 0.05 },
    ] : [],
    status: mode === 'two_conditions' ? 'not_applicable' : 'ok',
    note: mode === 'two_conditions' ? '仅三条件全局检验有意义时才执行事后检验' : 'Tukey HSD 事后检验',
  }))

  return {
    mode,
    conditions,
    total_sessions: conditions.length * 2,
    sessions_by_condition: Object.fromEntries(conditions.map((c) => [c, 2])),
    excluded_sessions: [],
    metrics,
    normality,
    statistical_tests,
    post_hoc_tests,
    observations: [],
  }
}

function makeMockReportWithExcluded() {
  const base = makeMockReport('two_conditions')
  return {
    ...base,
    total_sessions: 1,
    sessions_by_condition: { no_assistance: 0, glasses: 1 },
    excluded_sessions: [
      {
        session_id: 's-excluded-1',
        group_id: 'g-na-1',
        group_name: '无辅助小组 A',
        condition: 'no_assistance',
        uncoded_count: 2,
        total_count: 5,
      },
    ],
  }
}

// ── helpers ──────────────────────────────────────────────────────────────────

async function loginAsAdmin(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('后台密钥').fill(ADMIN_API_KEY)
  await page.getByRole('button', { name: '进入后台' }).click()
  await expect(page).toHaveURL(/\/admin\/users/)
}

async function mockGroupsAndAnalysis(
  page: import('@playwright/test').Page,
  reportOverride?: object,
): Promise<void> {
  await page.route('**/api/admin/groups/**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_GROUPS) })
    } else {
      await route.fallback()
    }
  })

  await page.route('**/api/admin/coi-analysis/**', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as { mode: string }
      const report = reportOverride ?? makeMockReport(payload.mode as 'two_conditions' | 'three_conditions')
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(report) })
    } else {
      await route.fallback()
    }
  })
}

async function selectGroupsAndGenerate(page: import('@playwright/test').Page): Promise<void> {
  // 点开第一个条件的样本选择按钮（无辅助）
  const sampleFields = page.locator('.sample-field')
  await sampleFields.first().locator('.sample-select-trigger').click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('button', { name: '完成' }).click()

  // 点开第二个条件（智能眼镜）
  await sampleFields.nth(1).locator('.sample-select-trigger').click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('button', { name: '完成' }).click()

  // 生成分析
  await page.getByRole('button', { name: '生成分析' }).click()
  await expect(page.locator('.coi-analysis-page')).toBeVisible()
}

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe('Admin CoI 认知参与度分析页面', () => {
  test('菜单导航到 CoI 认知参与度分析页', async ({ page }) => {
    await loginAsAdmin(page)
    await page.getByText('CoI 认知参与度分析').click()
    await expect(page).toHaveURL(/\/admin\/coi-analysis/)
    await expect(page.getByRole('heading', { name: 'CoI 认知参与度分析' })).toBeVisible()
  })

  test('页面初始状态：显示模式切换、样本选择、生成按钮', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')

    await expect(page.getByText('两条件')).toBeVisible()
    await expect(page.getByText('三条件')).toBeVisible()
    await expect(page.getByRole('button', { name: '生成分析' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下载 HTML 报告' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '打印 / PDF' })).toBeDisabled()
  })

  test('两条件模式：生成分析后显示各统计区块', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    // 概览卡片
    await expect(page.getByText('纳入会话数')).toBeVisible()
    await expect(page.locator('.summary-label').filter({ hasText: '无辅助' }).first()).toBeVisible()
    await expect(page.locator('.summary-label').filter({ hasText: '智能眼镜' }).first()).toBeVisible()

    // 描述统计
    await expect(page.getByText('描述性统计')).toBeVisible()
    await expect(page.getByText('Triggering Event 比例').first()).toBeVisible()
    await expect(page.getByText('高阶认知参与比例 (IN+RE)').first()).toBeVisible()
    await expect(page.getByText('认知参与加权得分').first()).toBeVisible()

    // 正态性检查
    await expect(page.getByText('正态性检查')).toBeVisible()
    await expect(page.getByText('Shapiro-Wilk')).toBeVisible()

    // 推断统计
    await expect(page.getByText('推断统计结果')).toBeVisible()
    await expect(page.getByText('Independent-samples t-test').first()).toBeVisible()

    // 均值对比图
    await expect(page.getByText('各指标均值对比')).toBeVisible()
  })

  test('两条件模式：不显示事后检验区块', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    await expect(page.getByText('事后检验（Post-hoc）')).not.toBeVisible()
  })

  test('切换到三条件模式：显示 APP 通知条件，事后检验可见', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')

    // 切换到三条件
    await page.locator('.el-segmented__item').filter({ hasText: '三条件' }).click()
    await expect(page.locator('.sample-field label').filter({ hasText: 'APP 通知' }).first()).toBeVisible()

    // 选三个条件的样本
    const sampleFields = page.locator('.sample-field')
    for (let i = 0; i < 3; i++) {
      await sampleFields.nth(i).locator('.sample-select-trigger').click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await page.getByRole('button', { name: '全选' }).click()
      await page.getByRole('button', { name: '完成' }).click()
    }

    await page.getByRole('button', { name: '生成分析' }).click()

    await expect(page.getByText('事后检验（Post-hoc）')).toBeVisible()
    await expect(page.getByText('One-way ANOVA').first()).toBeVisible()
  })

  test('有排除会话时显示警告', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page, makeMockReportWithExcluded())
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    await expect(page.getByText(/有 1 个会话因存在未编码发言被排除/)).toBeVisible()
    await expect(page.locator('.excluded-item').getByText('无辅助小组 A')).toBeVisible()
    await expect(page.getByText(/2 条未编码/)).toBeVisible()
  })

  test('没有排除会话时不显示警告', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    await expect(page.getByText(/因存在未编码发言被排除/)).not.toBeVisible()
  })

  test('生成分析后下载和打印按钮启用', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    await expect(page.getByRole('button', { name: '下载 HTML 报告' })).toBeEnabled()
    await expect(page.getByRole('button', { name: '打印 / PDF' })).toBeEnabled()
  })

  test('未选样本时点生成分析显示警告', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')

    await page.getByRole('button', { name: '生成分析' }).click()
    await expect(page.getByText(/请为.+选择要纳入分析的小组/)).toBeVisible()
  })

  test('下载 HTML 报告生成文件', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', '下载在部分浏览器环境下不稳定')

    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: '下载 HTML 报告' }).click(),
    ])
    expect(download.suggestedFilename()).toMatch(/coi-analysis-report.*\.html/)
  })

  test('API 返回错误时显示错误提示', async ({ page }) => {
    await loginAsAdmin(page)
    await page.route('**/api/admin/groups/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_GROUPS) })
    })
    await page.route('**/api/admin/coi-analysis/**', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'internal error' }) })
    })

    await page.goto('/admin/coi-analysis')

    const sampleFields = page.locator('.sample-field')
    await sampleFields.first().locator('.sample-select-trigger').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: '全选' }).click()
    await page.getByRole('button', { name: '完成' }).click()
    await sampleFields.nth(1).locator('.sample-select-trigger').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: '全选' }).click()
    await page.getByRole('button', { name: '完成' }).click()

    await page.getByRole('button', { name: '生成分析' }).click()
    await expect(page.getByText(/生成 CoI 分析失败|internal error/)).toBeVisible({ timeout: 8000 })
  })

  test('描述统计表显示 6 个指标行', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    const descriptiveCard = page.locator('.el-card').filter({ hasText: '描述性统计' })
    await expect(descriptiveCard.locator('.el-table__body tr')).toHaveCount(6)
  })

  test('正态性检验表两条件显示 12 行（6指标×2条件）', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    const normalityCard = page.locator('.el-card').filter({ hasText: '正态性检查' })
    await expect(normalityCard.locator('.el-table__body tr')).toHaveCount(12)
  })

  test('推断统计表显示 6 行', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    const inferentialCard = page.locator('.el-card').filter({ hasText: '推断统计结果' })
    await expect(inferentialCard.locator('.el-table__body tr')).toHaveCount(6)
  })

  test('两条件模式描述统计显示均值差列', async ({ page }) => {
    await loginAsAdmin(page)
    await mockGroupsAndAnalysis(page)
    await page.goto('/admin/coi-analysis')
    await selectGroupsAndGenerate(page)

    await expect(page.getByText('均值差').first()).toBeVisible()
    await expect(page.getByText('智能眼镜 - 无辅助').first()).toBeVisible()
  })
})
