<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appLogin } from '../../api/appAuth'
import {
  DEFAULT_EXPERIMENT_DEVICE_TOKEN,
  EXPERIMENT_DEVICES,
  isKnownExperimentDeviceToken,
} from '../../constants/experimentDevices'
import { getJPushDeviceToken } from '../../native/jpushDevice'
import { extractErrorMessage } from '../../utils/error'

const router = useRouter()
const route = useRoute()

const name = ref('')
const password = ref('')
const currentDeviceToken = ref('')
const selectedDeviceToken = ref<string>(DEFAULT_EXPERIMENT_DEVICE_TOKEN)
const loading = ref(false)
const error = ref('')

const deviceOptions = computed(() => {
  const token = currentDeviceToken.value
  if (token && !isKnownExperimentDeviceToken(token)) {
    return [
      {
        key: 'current_app_device',
        label: '当前手机设备',
        deviceToken: token,
      },
      ...EXPERIMENT_DEVICES,
    ]
  }
  return EXPERIMENT_DEVICES
})

onMounted(async () => {
  try {
    const token = await getJPushDeviceToken()
    if (token) {
      currentDeviceToken.value = token
      selectedDeviceToken.value = token
    }
  } catch {
    selectedDeviceToken.value = DEFAULT_EXPERIMENT_DEVICE_TOKEN
  }
})

async function handleSubmit() {
  error.value = ''
  if (!name.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  try {
    const res = await appLogin({
      name: name.value.trim(),
      password: password.value,
      device_token: selectedDeviceToken.value,
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

</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">用户登录</h1>
      <p class="auth-subtitle">使用用户名登录 Collab AI</p>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <label class="auth-label">
          用户名
          <input
            v-model="name"
            class="auth-input"
            type="text"
            placeholder="你的用户名"
            autocomplete="username"
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

        <label class="auth-label">
          当前手机设备
          <select v-model="selectedDeviceToken" class="auth-input">
            <option
              v-for="device in deviceOptions"
              :key="device.key"
              :value="device.deviceToken"
            >
              {{ device.label }}
            </option>
          </select>
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
