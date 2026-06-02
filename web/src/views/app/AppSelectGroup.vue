<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppEmptyState from '../../components/AppEmptyState.vue'
import { joinGroup, listDiscoverGroups, listMyGroups } from '../../api/appGroups'
import type { AppDiscoverGroup, AppGroupSummary } from '../../api/appGroups'
import { extractErrorMessage } from '../../utils/error'

interface AppCurrentGroup {
  id: string
  name: string
  condition?: string
}

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const groups = ref<AppGroupSummary[]>([])
const discoverGroups = ref<AppDiscoverGroup[]>([])
const selectedGroupId = ref(loadCurrentGroupFromStorage()?.id ?? '')
const error = ref('')

const selectedGroup = computed(() => groups.value.find((group) => group.id === selectedGroupId.value) ?? null)
const selectedDiscoverGroup = computed(
  () => discoverGroups.value.find((group) => group.id === selectedGroupId.value) ?? null,
)
const hasSelectableGroups = computed(() => groups.value.length > 0 || discoverGroups.value.length > 0)

function loadCurrentGroupFromStorage(): AppCurrentGroup | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_current_group')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppCurrentGroup
  } catch {
    return null
  }
}

function saveCurrentGroupToStorage(group: AppCurrentGroup | null) {
  if (typeof window === 'undefined') return
  if (!group) {
    window.localStorage.removeItem('app_current_group')
  } else {
    window.localStorage.setItem('app_current_group', JSON.stringify(group))
  }
}

function resolveRedirect(): string {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/app') && redirect !== '/app/select-group') {
    return redirect
  }
  return '/app'
}

async function loadGroups() {
  loading.value = true
  error.value = ''
  try {
    const [myGroups, joinableGroups] = await Promise.all([
      listMyGroups(),
      listDiscoverGroups({ limit: 200 }),
    ])
    groups.value = myGroups
    discoverGroups.value = joinableGroups

    if (!myGroups.length && !joinableGroups.length) {
      selectedGroupId.value = ''
      saveCurrentGroupToStorage(null)
      return
    }

    const storedId = selectedGroupId.value
    const storedGroup = storedId ? myGroups.find((group) => group.id === storedId) : null
    selectedGroupId.value = (storedGroup ?? myGroups[0] ?? joinableGroups[0])?.id ?? ''
  } catch (e) {
    console.error(e)
    error.value = extractErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function confirmGroup() {
  const selected = selectedGroup.value ?? selectedDiscoverGroup.value
  if (!selected) {
    ElMessage.warning('请选择本次登录要使用的小组')
    return
  }

  loading.value = true
  error.value = ''
  try {
    if (selectedDiscoverGroup.value && !selectedGroup.value) {
      const detail = await joinGroup(selectedDiscoverGroup.value.id)
      saveCurrentGroupToStorage({ id: detail.group.id, name: detail.group.name, condition: detail.group.condition })
    } else {
      saveCurrentGroupToStorage({
        id: selected.id,
        name: selected.name,
        condition: selected.condition,
      })
    }
    await router.replace(resolveRedirect())
  } catch (e) {
    console.error(e)
    error.value = extractErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function goGroupsPage() {
  await router.replace('/app/groups')
}

onMounted(() => {
  void loadGroups()
})
</script>

<template>
  <div class="select-group-page">
    <section class="select-group-panel">
      <h1 class="select-group-title">选择本次小组</h1>
      <p class="select-group-subtitle">请选择本次登录后要使用的小组。</p>

      <div v-if="loading" class="select-group-loading">小组加载中...</div>

      <AppEmptyState
        v-else-if="!hasSelectableGroups"
        icon="group"
        title="暂无可选小组"
        description="请联系管理员在后台创建小组，或确认小组人数未满。"
        compact
      />

      <template v-else>
        <label class="select-group-label">
          本次登录小组
          <select v-model="selectedGroupId" class="select-group-select">
            <optgroup v-if="groups.length" label="我的小组">
              <option
                v-for="group in groups"
                :key="group.id"
                :value="group.id"
              >
                {{ group.name }}（{{ group.member_count }} 人）
              </option>
            </optgroup>
            <optgroup v-if="discoverGroups.length" label="可加入小组">
              <option
                v-for="group in discoverGroups"
                :key="group.id"
                :value="group.id"
              >
                {{ group.name }}（{{ group.member_count }} 人）
              </option>
            </optgroup>
          </select>
        </label>

        <button class="select-group-button" type="button" @click="confirmGroup">
          进入
        </button>
      </template>

      <p v-if="error" class="select-group-error">{{ error }}</p>
      <button v-if="!loading && !hasSelectableGroups" class="select-group-secondary" type="button" @click="goGroupsPage">
        查看小组页
      </button>
    </section>
  </div>
</template>

<style scoped>
.select-group-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: radial-gradient(circle at top, #4f46e5 0, #020617 45%, #020617 100%);
  color: #e5e7eb;
}

.select-group-panel {
  width: 100%;
  max-width: 420px;
  padding: 28px 26px 30px;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.92);
  box-shadow: 0 22px 45px rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(16px);
}

.select-group-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  color: #e5e7eb;
}

.select-group-subtitle,
.select-group-loading,
.select-group-error {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.5;
  color: #9ca3af;
}

.select-group-error {
  margin-top: 12px;
  color: #fca5a5;
}

.select-group-label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 13px;
  font-weight: 400;
  color: #e5e7eb;
}

.select-group-select {
  width: 100%;
  min-height: 38px;
  border-radius: 10px;
  border: 1px solid #4b5563;
  padding: 0 11px;
  font-size: 14px;
  color: #e5e7eb;
  background: rgba(15, 23, 42, 0.85);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}

.select-group-select:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 1px rgba(79, 70, 229, 0.5);
  background: rgba(15, 23, 42, 0.98);
}

.select-group-button,
.select-group-secondary {
  width: 100%;
  min-height: 38px;
  border-radius: 999px;
  border: none;
  padding: 9px 14px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.1s ease, opacity 0.1s ease;
}

.select-group-button {
  background: linear-gradient(to right, #4f46e5, #6366f1);
  color: #e5e7eb;
}

.select-group-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.45);
}

.select-group-secondary {
  margin-top: 12px;
  border: 1px solid #4b5563;
  background: rgba(15, 23, 42, 0.85);
  color: #e5e7eb;
}
</style>
