import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import AdminLogin from '../views/admin/AdminLogin.vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import AppLayout from '../layouts/AppLayout.vue'
import AppHome from '../views/app/AppHome.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/app',
  },
  // 用户端 APP 路由
  {
    path: '/app',
    component: AppLayout,
    children: [
      {
        path: '',
        name: 'AppHome',
        component: AppHome,
      },
      {
        path: 'groups',
        name: 'AppGroups',
        component: () => import('../views/app/AppGroups.vue'),
      },
      {
        path: 'sessions',
        name: 'AppSessions',
        component: () => import('../views/app/AppSessions.vue'),
      },
    ],
  },
  // 管理后台路由
  {
    path: '/admin/login',
    name: 'AdminLogin',
    component: AdminLogin,
  },
  {
    path: '/admin',
    component: AdminLayout,
    children: [
      {
        path: '',
        redirect: '/admin/users',
      },
      {
        path: 'users',
        name: 'AdminUsers',
        component: () => import('../views/admin/AdminUsersPage.vue'),
      },
      {
        path: 'groups',
        name: 'AdminGroups',
        component: () => import('../views/admin/AdminGroupsPage.vue'),
      },
      {
        path: 'memberships',
        name: 'AdminMemberships',
        component: () => import('../views/admin/AdminMembershipsPage.vue'),
      },
      {
        path: 'chat-sessions',
        name: 'AdminChatSessions',
        component: () => import('../views/admin/AdminChatSessionsPage.vue'),
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router

