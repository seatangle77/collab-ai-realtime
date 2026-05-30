<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appRegister } from '../../api/appAuth'
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
const confirmPassword = ref('')
const currentDeviceToken = ref('')
const selectedDeviceToken = ref<string>(DEFAULT_EXPERIMENT_DEVICE_TOKEN)
const loading = ref(false)
const error = ref('')
const success = ref('')

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
  success.value = ''

  if (!name.value.trim()) {
    error.value = '请输入用户名'
    return
  }
  if (!password.value || password.value.length !== 4) {
    error.value = '请输入 4 位密码'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }

  loading.value = true
  try {
    await appRegister({
      name: name.value.trim(),
      password: password.value,
      device_token: selectedDeviceToken.value,
    })
    success.value = '注册成功，请使用用户名和密码登录'
    setTimeout(() => {
      const redirect = (route.query.redirect as string | undefined) || '/app'
      router.push({ path: '/app/login', query: { redirect } })
    }, 800)
  } catch (e: unknown) {
    error.value = extractErrorMessage(e) || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function goLogin() {
  const redirect = (route.query.redirect as string | undefined) || '/app'
  router.push({ path: '/app/login', query: { redirect } })
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">创建账号</h1>
      <p class="auth-subtitle">设置用户名和密码，开始使用 Collab AI</p>

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
            autocomplete="new-password"
          />
        </label>

        <label class="auth-label">
          确认密码
          <input
            v-model="confirmPassword"
            class="auth-input"
            type="password"
            placeholder="再次输入密码"
            autocomplete="new-password"
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
        <p v-if="success" class="auth-success">
          {{ success }}
        </p>

        <button class="auth-button" type="submit" :disabled="loading">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="auth-footer">
        已有账号？
        <button type="button" class="auth-link" @click="goLogin">
          立即登录
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
  background: radial-gradient(circle at top, #22c55e 0, #020617 45%, #020617 100%);
  color: #e5e7eb;
}

.auth-card {
  width: 100%;
  max-width: 440px;
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
  border-color: #22c55e;
  box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.5);
  background: rgba(15, 23, 42, 0.98);
}

.auth-error {
  margin: 0;
  font-size: 13px;
  color: #fca5a5;
}

.auth-success {
  margin: 0;
  font-size: 13px;
  color: #bbf7d0;
}

.auth-button {
  margin-top: 4px;
  border-radius: 999px;
  border: none;
  padding: 9px 14px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: linear-gradient(to right, #22c55e, #4ade80);
  color: #022c22;
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

@media (max-width: 600px) {
  .auth-page {
    min-height: 100svh;
    align-items: flex-start;
    padding-top: max(72px, calc(env(safe-area-inset-top) + 56px));
    padding-bottom: 28px;
  }

  .auth-card {
    border-radius: 16px;
  }
}
</style>
