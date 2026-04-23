import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './admin-helpers'

const GROUPS = [
  {
    title: '基础数据',
    items: [
      { label: '用户管理', path: '/admin/users', heading: '用户管理' },
      { label: '群组管理', path: '/admin/groups', heading: '群组管理' },
      { label: '成员关系', path: '/admin/memberships', heading: '成员关系管理' },
      { label: '会话管理', path: '/admin/chat-sessions', heading: '会话管理' },
      { label: '声纹管理', path: '/admin/voice-profiles', heading: '声纹管理' },
      { label: '语音转写', path: '/admin/speech-transcripts', heading: '语音转写' },
    ],
  },
  {
    title: 'AI 分析',
    items: [
      { label: '讨论状态', path: '/admin/discussion-states', heading: '讨论状态' },
      { label: '窗口指标', path: '/admin/window-metrics', heading: '窗口指标' },
      { label: '窗口关键词', path: '/admin/window-metrics-keywords', heading: '窗口关键词' },
      { label: '窗口论证批量日志', path: '/admin/window-metrics-batch-reasoning', heading: '窗口论证批量日志' },
      { label: '讨论摘要', path: '/admin/discussion-summaries', heading: '讨论摘要' },
      { label: '信息缺口按钮', path: '/admin/info-gap-buttons', heading: '信息缺口按钮' },
      { label: '关键词 SKW', path: '/admin/info-gap-skw', heading: '关键词 SKW' },
      { label: 'AI 推送分析', path: '/admin/ai-push-analysis', heading: 'AI 推送分析' },
      { label: '关键词召回分析', path: '/admin/info-gap-recall-analysis', heading: '关键词召回分析' },
    ],
  },
  {
    title: '推送管理',
    items: [
      { label: '推送队列', path: '/admin/push-queue', heading: '推送队列' },
      { label: '推送日志', path: '/admin/push-logs', heading: '推送日志' },
    ],
  },
]

test.describe.serial('Admin 导航菜单重构', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('1. 左侧显示 3 个分组标题与 17 个菜单项', async ({ page }) => {
    const totalItems = GROUPS.reduce((sum, group) => sum + group.items.length, 0)

    for (const group of GROUPS) {
      await expect(page.locator('.el-menu-item-group__title').filter({ hasText: group.title })).toBeVisible()
      for (const item of group.items) {
        await expect(page.locator('.admin-menu .el-menu-item').filter({ hasText: item.label })).toBeVisible()
      }
    }

    await expect(page.locator('.admin-menu .el-menu-item')).toHaveCount(totalItems)
  })

  test('2. 菜单项可点击并跳到对应页面', async ({ page }) => {
    for (const group of GROUPS) {
      for (const item of group.items) {
        await page.locator('.admin-menu .el-menu-item').filter({ hasText: item.label }).click()
        await expect(page).toHaveURL(new RegExp(item.path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
        await expect(page.getByRole('heading', { name: item.heading })).toBeVisible()
      }
    }
  })

  test('4. 点击 toggle 按钮可收起侧边栏', async ({ page }) => {
    const toggleBtn = page.locator('.admin-header button').first()
    await expect(page.locator('.admin-menu .el-menu-item').first()).toBeVisible()
    await toggleBtn.click()
    await expect(page.locator('.el-aside')).toHaveAttribute('style', /width:\s*0px/)
  })

  test('5. 再次点击 toggle 按钮可展开侧边栏', async ({ page }) => {
    const toggleBtn = page.locator('.admin-header button').first()
    await toggleBtn.click()
    await toggleBtn.click()
    await expect(page.locator('.el-aside')).toHaveAttribute('style', /width:\s*220px/)
    await expect(page.locator('.admin-menu .el-menu-item').first()).toBeVisible()
  })

  test('3. 刷新后当前菜单项保持高亮', async ({ page }) => {
    await page.goto('/admin/info-gap-recall-analysis')
    await expect(page.getByRole('heading', { name: '关键词召回分析' })).toBeVisible()

    const activeBeforeReload = page.locator('.admin-menu .el-menu-item.is-active')
    await expect(activeBeforeReload).toContainText('关键词召回分析')

    await page.reload()
    await expect(page.getByRole('heading', { name: '关键词召回分析' })).toBeVisible()

    const activeAfterReload = page.locator('.admin-menu .el-menu-item.is-active')
    await expect(activeAfterReload).toContainText('关键词召回分析')
  })
})
