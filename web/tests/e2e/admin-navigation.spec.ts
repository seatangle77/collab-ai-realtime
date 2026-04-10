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
      { label: '文字消息', path: '/admin/session-text-messages', heading: '文字消息' },
    ],
  },
  {
    title: 'AI 分析',
    items: [
      { label: '讨论状态', path: '/admin/discussion-states', heading: '讨论状态' },
      { label: '参与度指标', path: '/admin/engagement-metrics', heading: '参与度指标' },
      { label: '窗口指标', path: '/admin/window-metrics', heading: '窗口指标' },
      { label: '讨论摘要', path: '/admin/discussion-summaries', heading: '讨论摘要' },
      { label: '信息缺口按钮', path: '/admin/info-gap-buttons', heading: '信息缺口按钮' },
      { label: '关键词 SKW', path: '/admin/keyword-skw', heading: '关键词 SKW' },
    ],
  },
  {
    title: '推送管理',
    items: [
      { label: '推送队列', path: '/admin/push-queue', heading: '推送队列' },
      { label: '推送日志', path: '/admin/push-logs', heading: '推送日志' },
    ],
  },
  {
    title: '系统配置',
    items: [
      { label: '讨论规则', path: '/admin/discussion-rules', heading: '讨论规则配置' },
    ],
  },
]

test.describe.serial('Admin 导航菜单重构', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('1. 左侧显示 4 个分组标题与 15 个菜单项', async ({ page }) => {
    for (const group of GROUPS) {
      await expect(page.locator('.el-menu-item-group__title').filter({ hasText: group.title })).toBeVisible()
      for (const item of group.items) {
        await expect(page.locator('.admin-menu .el-menu-item').filter({ hasText: item.label })).toBeVisible()
      }
    }
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

  test('3. 刷新后当前菜单项保持高亮', async ({ page }) => {
    await page.goto('/admin/discussion-rules')
    await expect(page.getByRole('heading', { name: '讨论规则配置' })).toBeVisible()

    const activeBeforeReload = page.locator('.admin-menu .el-menu-item.is-active')
    await expect(activeBeforeReload).toContainText('讨论规则')

    await page.reload()
    await expect(page.getByRole('heading', { name: '讨论规则配置' })).toBeVisible()

    const activeAfterReload = page.locator('.admin-menu .el-menu-item.is-active')
    await expect(activeAfterReload).toContainText('讨论规则')
  })
})
