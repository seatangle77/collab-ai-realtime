<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appLogin } from '../../api/appAuth'
import { getJPushDeviceToken } from '../../native/jpushDevice'
import { sendLocalTestNotification } from '../../native/localTestNotification'
import { extractErrorMessage } from '../../utils/error'

const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const loading = ref(false)
const deviceTokenLoading = ref(false)
const localNotificationLoading = ref(false)
const error = ref('')
const deviceToken = ref('')
const deviceTokenError = ref('')
const deviceTokenHint = ref('')
const localNotificationMessage = ref('')
const localNotificationError = ref('')

async function handleSubmit() {
  error.value = ''
  if (!email.value.trim() || !password.value) {
    error.value = '请输入邮箱和密码'
    return
  }

  loading.value = true
  try {
    const res = await appLogin({
      email: email.value.trim(),
      password: password.value,
    })
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('app_access_token', res.access_token)
      window.localStorage.setItem('app_user', JSON.stringify(res.user))
      window.localStorage.removeItem('app_current_group')
    }

    const needsReset = !!res.user.password_needs_reset
    if (needsReset) {
      await router.push('/app/change-password')
      return
    }

    const redirect = (route.query.redirect as string | undefined) || '/app'
    await router.push(redirect)
  } catch (e: unknown) {
    error.value = extractErrorMessage(e) || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function goRegister() {
  const redirect = (route.query.redirect as string | undefined) || '/app'
  router.push({ path: '/app/register', query: { redirect } })
}

async function showDeviceToken() {
  deviceToken.value = ''
  deviceTokenError.value = ''
  deviceTokenHint.value = '正在获取极光 device_token...'
  deviceTokenLoading.value = true

  try {
    let token = ''
    for (let i = 0; i < 8; i += 1) {
      token = await getJPushDeviceToken()
      if (token) break
      await new Promise((resolve) => window.setTimeout(resolve, 1000))
    }

    if (!token) {
      deviceTokenError.value = '极光 device_token 还在注册中，请稍后再试'
      return
    }
    deviceToken.value = token
  } catch (e: unknown) {
    deviceTokenError.value = extractErrorMessage(e) || '读取 device_token 失败'
  } finally {
    deviceTokenHint.value = ''
    deviceTokenLoading.value = false
  }
}

async function sendLocalNotification() {
  localNotificationMessage.value = ''
  localNotificationError.value = ''
  localNotificationLoading.value = true

  try {
    await sendLocalTestNotification()
    localNotificationMessage.value = '本地测试通知已发送'
  } catch (e: unknown) {
    localNotificationError.value = extractErrorMessage(e) || '发送本地通知失败'
  } finally {
    localNotificationLoading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">用户登录</h1>
      <p class="auth-subtitle">使用注册邮箱登录 Collab AI</p>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <label class="auth-label">
          邮箱
          <input
            v-model="email"
            class="auth-input"
            type="email"
            placeholder="you@example.com"
            autocomplete="email"
          />
        </label>

        <label class="auth-label">
          密码
          <input
            v-model="password"
            class="auth-input"
            type="password"
            placeholder="4 位密码"
            autocomplete="current-password"
          />
        </label>

        <p v-if="error" class="auth-error">
          {{ error }}
        </p>

        <button class="auth-button" type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <p class="auth-footer">
        还没有账号？
        <button type="button" class="auth-link" @click="goRegister">
          立即注册
        </button>
      </p>

      <div class="device-token-panel">
        <button
          type="button"
          class="device-token-button"
          :disabled="deviceTokenLoading"
          @click="showDeviceToken"
        >
          {{ deviceTokenLoading ? '读取中...' : '显示 device_token' }}
        </button>
        <p v-if="deviceTokenHint" class="device-token-hint">{{ deviceTokenHint }}</p>
        <p v-if="deviceTokenError" class="device-token-error">{{ deviceTokenError }}</p>
        <p v-if="deviceToken" class="device-token-value">{{ deviceToken }}</p>
        <button
          type="button"
          class="device-token-button device-token-button--secondary"
          :disabled="localNotificationLoading"
          @click="sendLocalNotification"
        >
          {{ localNotificationLoading ? '发送中...' : '发送本地测试通知' }}
        </button>
        <p v-if="localNotificationMessage" class="device-token-success">
          {{ localNotificationMessage }}
        </p>
        <p v-if="localNotificationError" class="device-token-error">{{ localNotificationError }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top, #4f46e5 0, #020617 45%, #020617 100%);
  color: #e5e7eb;
}

.auth-card {
  width: 100%;
  max-width: 420px;
  padding: 28px 26px 30px;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.92);
  box-shadow: 0 22px 45px rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(16px);
}

.auth-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.auth-subtitle {
  margin: 0 0 18px;
  font-size: 13px;
  color: #9ca3af;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.auth-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.auth-input {
  border-radius: 10px;
  border: 1px solid #4b5563;
  padding: 9px 11px;
  font-size: 14px;
  color: #e5e7eb;
  background: rgba(15, 23, 42, 0.85);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}

.auth-input:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 1px rgba(79, 70, 229, 0.5);
  background: rgba(15, 23, 42, 0.98);
}

.auth-error {
  margin: 0;
  font-size: 13px;
  color: #fca5a5;
}

.auth-button {
  margin-top: 4px;
  border-radius: 999px;
  border: none;
  padding: 9px 14px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: linear-gradient(to right, #4f46e5, #6366f1);
  color: #e5e7eb;
  transition: transform 0.1s ease, box-shadow 0.1s ease, opacity 0.1s ease;
}

.auth-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.45);
}

.auth-button:disabled {
  opacity: 0.6;
  cursor: default;
}

.auth-footer {
  margin-top: 16px;
  font-size: 13px;
  color: #9ca3af;
}

.auth-link {
  border: none;
  background: none;
  color: #e5e7eb;
  cursor: pointer;
  text-decoration: underline;
  padding: 0 2px;
  font-size: 13px;
}

.device-token-panel {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.25);
}

.device-token-button {
  width: 100%;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  padding: 9px 12px;
  background: rgba(15, 23, 42, 0.65);
  color: #e5e7eb;
  cursor: pointer;
  font-size: 13px;
}

.device-token-button:disabled {
  opacity: 0.6;
  cursor: default;
}

.device-token-button--secondary {
  margin-top: 10px;
  border-color: rgba(96, 165, 250, 0.55);
  background: rgba(30, 64, 175, 0.35);
}

.device-token-error {
  margin: 10px 0 0;
  color: #fca5a5;
  font-size: 12px;
}

.device-token-hint {
  margin: 10px 0 0;
  color: #cbd5e1;
  font-size: 12px;
}

.device-token-success {
  margin: 10px 0 0;
  color: #bbf7d0;
  font-size: 12px;
}

.device-token-value {
  margin: 10px 0 0;
  padding: 10px;
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.72);
  color: #bfdbfe;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

@media (max-width: 600px) {
  .auth-page {
    min-height: 100svh;
    align-items: flex-start;
    padding-top: max(92px, calc(env(safe-area-inset-top) + 72px));
    padding-bottom: 28px;
  }

  .auth-card {
    border-radius: 16px;
  }
}
</style>
