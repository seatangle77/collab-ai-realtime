<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const token = ref(localStorage.getItem('admin_api_key') ?? '')
const error = ref('')
const loading = ref(false)

async function handleSubmit() {
  error.value = ''
  if (!token.value.trim()) {
    error.value = '请输入后台访问密钥'
    return
  }

  loading.value = true
  try {
    localStorage.setItem('admin_api_key', token.value.trim())
    await router.push('/admin/users')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="login-title">Admin 登录</h1>
      <p class="login-subtitle">请输入后端配置的 ADMIN_API_KEY 以访问管理后台。</p>

      <form class="login-form" @submit.prevent="handleSubmit">
        <label class="login-label">
          后台密钥
          <input
            v-model="token"
            class="login-input"
            type="password"
            placeholder="例如：TestAdminKey123"
          />
        </label>

        <p v-if="error" class="login-error">
          {{ error }}
        </p>

        <button class="login-button" type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '进入后台' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top, #1d4ed8 0, #020617 45%, #020617 100%);
  color: #e5e7eb;
}

.login-card {
  width: 100%;
  max-width: 420px;
  padding: 28px 26px 30px;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.92);
  box-shadow: 0 22px 45px rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(16px);
}

.login-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.login-subtitle {
  margin: 0 0 18px;
  font-size: 13px;
  color: #9ca3af;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.login-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.login-input {
  border-radius: 10px;
  border: 1px solid #4b5563;
  padding: 9px 11px;
  font-size: 14px;
  color: #e5e7eb;
  background: rgba(15, 23, 42, 0.85);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}

.login-input:focus {
  border-color: #f97316;
  box-shadow: 0 0 0 1px rgba(249, 115, 22, 0.45);
  background: rgba(15, 23, 42, 0.98);
}

.login-error {
  margin: 0;
  font-size: 13px;
  color: #fca5a5;
}

.login-button {
  margin-top: 4px;
  border-radius: 999px;
  border: none;
  padding: 9px 14px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: linear-gradient(to right, #f97316, #fb923c);
  color: #111827;
  transition: transform 0.1s ease, box-shadow 0.1s ease, opacity 0.1s ease;
}

.login-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.45);
}

.login-button:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>

