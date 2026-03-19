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
  // 用户端登录 / 注册
  {
    path: '/app/login',
    name: 'AppLogin',
    component: () => import('../views/app/AppLogin.vue'),
  },
  {
    path: '/app/register',
    name: 'AppRegister',
    component: () => import('../views/app/AppRegister.vue'),
  },
  {
    path: '/app/change-password',
    name: 'AppChangePassword',
    component: () => import('../views/app/AppChangePassword.vue'),
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
        path: 'groups/:id',
        name: 'AppGroupDetail',
        component: () => import('../views/app/AppGroupDetail.vue'),
      },
      {
        path: 'sessions',
        name: 'AppSessions',
        component: () => import('../views/app/AppSessions.vue'),
      },
      {
        path: 'voice-profile',
        name: 'AppVoiceProfile',
        component: () => import('../views/app/AppVoiceProfile.vue'),
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
        path: 'groups/:id',
        name: 'AdminGroupDetail',
        component: () => import('../views/admin/AdminGroupDetailPage.vue'),
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
      {
        path: 'voice-profiles',
        name: 'AdminVoiceProfiles',
        component: () => import('../views/admin/AdminVoiceProfilesPage.vue'),
      },
      {
        path: 'voice-profiles/:id',
        name: 'AdminVoiceProfileDetail',
        component: () => import('../views/admin/AdminVoiceProfileDetail.vue'),
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const publicAppPaths = ['/app/login', '/app/register']
  if (typeof window === 'undefined') {
    next()
    return
  }

  const token = window.localStorage.getItem('app_access_token')
  const userRaw = window.localStorage.getItem('app_user')
  let needsReset = false
  if (userRaw) {
    try {
      const parsed = JSON.parse(userRaw)
      needsReset = !!parsed?.password_needs_reset
    } catch {
      needsReset = false
    }
  }

  // 已登录用户访问登录/注册页
  if (token && publicAppPaths.includes(to.path)) {
    if (needsReset) {
      next('/app/change-password')
    } else {
      next('/app')
    }
    return
  }

  // 已登录且需要修改密码时，强制跳转到改密码页（仅允许访问该页）
  if (token && needsReset) {
    if (to.path === '/app/change-password' || to.path.startsWith('/admin')) {
      next()
      return
    }
    if (to.path.startsWith('/app')) {
      next('/app/change-password')
      return
    }
  }

  // 未登录访问受保护的 /app 路由时，跳转到登录页
  if (to.path.startsWith('/app') && !publicAppPaths.includes(to.path) && to.path !== '/app/change-password') {
    if (!token) {
      next({
        path: '/app/login',
        query: {
          redirect: to.fullPath,
        },
      })
      return
    }
  }

  next()
})

export default router
