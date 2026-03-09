<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appRegister } from '../../api/appAuth'

const router = useRouter()
const route = useRoute()

const name = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')

async function handleSubmit() {
  error.value = ''
  success.value = ''

  if (!name.value.trim()) {
    error.value = '请输入昵称'
    return
  }
  if (!email.value.trim()) {
    error.value = '请输入邮箱'
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
      email: email.value.trim(),
      password: password.value,
    })
    success.value = '注册成功，请使用该邮箱和密码登录'
    setTimeout(() => {
      const redirect = (route.query.redirect as string | undefined) || '/app'
      router.push({ path: '/app/login', query: { redirect } })
    }, 800)
  } catch (e: any) {
    error.value = e?.message || '注册失败，请稍后重试'
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
      <p class="auth-subtitle">注册成为 Collab AI 用户，开始协作与会话</p>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <label class="auth-label">
          昵称
          <input
            v-model="name"
            class="auth-input"
            type="text"
            placeholder="你的称呼"
            autocomplete="name"
          />
        </label>

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
</style>

