<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { changeAppPassword } from '../../api/appAuth'

const router = useRouter()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')

async function handleSubmit() {
  error.value = ''
  success.value = ''

  if (!oldPassword.value) {
    error.value = '请输入旧密码'
    return
  }
  if (!newPassword.value || newPassword.value.length !== 4) {
    error.value = '新密码必须为 4 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }

  loading.value = true
  try {
    const res = await changeAppPassword({
      old_password: oldPassword.value,
      new_password: newPassword.value,
    })

    if (typeof window !== 'undefined') {
      window.localStorage.setItem('app_user', JSON.stringify(res))
    }

    success.value = '密码修改成功'
    setTimeout(() => {
      router.push('/app')
    }, 600)
  } catch (e: any) {
    error.value = e?.message || '修改密码失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">修改密码</h1>
      <p class="auth-subtitle">出于安全原因，请更新您的登录密码</p>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <label class="auth-label">
          旧密码
          <input
            v-model="oldPassword"
            class="auth-input"
            type="password"
            placeholder="当前 4 位密码"
            autocomplete="current-password"
          />
        </label>

        <label class="auth-label">
          新密码
          <input
            v-model="newPassword"
            class="auth-input"
            type="password"
            placeholder="新的 4 位密码"
            autocomplete="new-password"
          />
        </label>

        <label class="auth-label">
          确认新密码
          <input
            v-model="confirmPassword"
            class="auth-input"
            type="password"
            placeholder="再次输入新的 4 位密码"
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
          {{ loading ? '提交中...' : '保存新密码' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top, #0f766e 0, #020617 45%, #020617 100%);
  color: #e5e7eb;
}

.auth-card {
  width: 100%;
  max-width: 430px;
  padding: 28px 26px 30px;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.94);
  box-shadow: 0 22px 45px rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(18px);
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
  border-color: #14b8a6;
  box-shadow: 0 0 0 1px rgba(20, 184, 166, 0.5);
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
  background: linear-gradient(to right, #14b8a6, #2dd4bf);
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
</style>

