<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminGroup, AdminMembership, AdminChatSession } from '../../types/admin'
import { getAdminGroup, updateAdminGroup, deleteAdminGroup } from '../../api/admin/groups'
import { listAdminMemberships, updateAdminMembership, deleteAdminMembership } from '../../api/admin/memberships'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import { formatDateTimeToCST } from '../../utils/datetime'

const route = useRoute()
const router = useRouter()
const groupId = route.params.id as string

// ── 页面状态 ──────────────────────────────────────────────
const group = ref<AdminGroup | null>(null)
const pageLoading = ref(true)
const error = ref('')

// 成员列表
const memberships = ref<AdminMembership[]>([])
const memberTotal = ref(0)
const memberPage = ref(1)
const memberPageSize = ref(10)
const memberLoading = ref(false)

// 会话列表
const sessions = ref<AdminChatSession[]>([])
const sessionTotal = ref(0)
const sessionPage = ref(1)
const sessionPageSize = ref(10)
const sessionLoading = ref(false)

// ── 编辑群组 dialog ───────────────────────────────────────
const editGroupVisible = ref(false)
const editGroupFormRef = ref<FormInstance>()
const editGroupForm = reactive({ name: '', is_active: true })
const editGroupRules: FormRules<typeof editGroupForm> = {
  name: [{ required: true, message: '请输入群组名称', trigger: 'blur' }],
}

function openEditGroup() {
  if (!group.value) return
  editGroupForm.name = group.value.name
  editGroupForm.is_active = group.value.is_active
  editGroupVisible.value = true
}

async function submitEditGroup() {
  if (!editGroupFormRef.value) return
  await editGroupFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const updated = await updateAdminGroup(groupId, {
        name: editGroupForm.name,
        is_active: editGroupForm.is_active,
      })
      group.value = updated
      editGroupVisible.value = false
      ElMessage.success('更新群组成功')
    } catch (e: any) {
      ElMessage.error(e?.message || '更新群组失败')
    }
  })
}

// ── 编辑成员 dialog ───────────────────────────────────────
const editMemberVisible = ref(false)
const editMemberForm = reactive({ id: '', role: 'member', status: 'active' })

function openEditMember(row: AdminMembership) {
  editMemberForm.id = row.id
  editMemberForm.role = row.role
  editMemberForm.status = row.status
  editMemberVisible.value = true
}

async function submitEditMember() {
  try {
    await updateAdminMembership(editMemberForm.id, {
      role: editMemberForm.role,
      status: editMemberForm.status,
    })
    editMemberVisible.value = false
    ElMessage.success('更新成员关系成功')
    await fetchMemberships(memberPage.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '更新成员关系失败')
  }
}

// ── 删除成员 ─────────────────────────────────────────────
async function handleDeleteMember(row: AdminMembership) {
  const displayName = row.user_name || row.user_id
  try {
    await ElMessageBox.confirm(`确认删除「${displayName}」的成员关系吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteAdminMembership(row.id)
    ElMessage.success('删除成员关系成功')
    if (memberships.value.length === 1 && memberPage.value > 1) {
      memberPage.value -= 1
    }
    await fetchMemberships(memberPage.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '删除成员关系失败')
  }
}

// ── 停用 / 启用群组 ──────────────────────────────────────
async function handleToggleActive() {
  if (!group.value) return
  const toActive = !group.value.is_active
  const label = toActive ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(`确认${label}该群组吗？`, `${label}确认`, {
      type: 'warning',
      confirmButtonText: label,
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    const updated = await updateAdminGroup(groupId, { is_active: toActive })
    group.value = updated
    ElMessage.success(`群组已${label}`)
  } catch (e: any) {
    ElMessage.error(e?.message || `${label}群组失败`)
  }
}

// ── 删除群组 ─────────────────────────────────────────────
async function handleDeleteGroup() {
  if (!group.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除群组「${group.value.name}」吗？该操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteAdminGroup(groupId)
    ElMessage.success('删除群组成功')
    router.push({ name: 'AdminGroups' })
  } catch (e: any) {
    ElMessage.error(e?.message || '删除群组失败')
  }
}

// ── 数据加载 ─────────────────────────────────────────────
async function fetchMemberships(page: number) {
  memberLoading.value = true
  try {
    const res = await listAdminMemberships({
      group_id: groupId,
      page,
      page_size: memberPageSize.value,
    })
    memberships.value = res.items
    memberTotal.value = res.meta.total
    memberPage.value = res.meta.page
  } catch (e: any) {
    ElMessage.error(e?.message || '加载成员列表失败')
  } finally {
    memberLoading.value = false
  }
}

async function fetchSessions(page: number) {
  sessionLoading.value = true
  try {
    const res = await listAdminChatSessions({
      group_id: groupId,
      page,
      page_size: sessionPageSize.value,
    })
    sessions.value = res.items
    sessionTotal.value = res.meta.total
    sessionPage.value = res.meta.page
  } catch (e: any) {
    ElMessage.error(e?.message || '加载会话列表失败')
  } finally {
    sessionLoading.value = false
  }
}

function sessionStatusLabel(status: string | null | undefined): string {
  if (status === 'not_started') return '未开始'
  if (status === 'ongoing') return '进行中'
  if (status === 'ended') return '已结束'
  return '未知'
}

function sessionStatusType(status: string | null | undefined): string {
  if (status === 'not_started') return 'info'
  if (status === 'ongoing') return 'success'
  if (status === 'ended') return ''
  return 'info'
}

onMounted(async () => {
  pageLoading.value = true
  error.value = ''

  const [groupResult] = await Promise.allSettled([getAdminGroup(groupId)])

  if (groupResult.status === 'fulfilled') {
    group.value = groupResult.value
    await Promise.all([fetchMemberships(1), fetchSessions(1)])
  } else {
    error.value = (groupResult.reason as any)?.message || '加载群组信息失败'
  }

  pageLoading.value = false
})
</script>

<template>
  <div class="admin-group-detail-page">
    <!-- 顶部导航 -->
    <div class="admin-group-detail-nav">
      <el-button text @click="router.push({ name: 'AdminGroups' })">← 返回群组列表</el-button>
      <span class="admin-group-detail-nav-title">{{ group?.name ?? groupId }}</span>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="admin-group-detail-error">
      <p class="admin-group-detail-error-msg">{{ error }}</p>
      <el-button @click="router.push({ name: 'AdminGroups' })">返回列表</el-button>
    </div>

    <template v-else-if="!pageLoading">
      <!-- 群组信息卡 -->
      <el-card class="admin-group-detail-card" shadow="never">
        <div class="admin-group-detail-info-header">
          <div>
            <div class="admin-group-detail-name-row">
              <h2 class="admin-group-detail-name">{{ group?.name }}</h2>
              <el-tag :type="group?.is_active ? 'success' : 'info'" size="small">
                {{ group?.is_active ? '启用' : '停用' }}
              </el-tag>
            </div>
            <div class="admin-group-detail-meta">
              <span class="admin-group-detail-id">ID：{{ group?.id }}</span>
              <span class="admin-group-detail-dot">·</span>
              <span>创建时间：{{ group ? formatDateTimeToCST(group.created_at) : '' }}</span>
            </div>
          </div>
          <el-button size="small" @click="openEditGroup">编辑</el-button>
        </div>
      </el-card>

      <!-- 成员列表卡 -->
      <el-card class="admin-group-detail-card" shadow="never">
        <h3 class="admin-group-detail-section-title">成员（{{ memberTotal }} 条）</h3>
        <el-table :data="memberships" v-loading="memberLoading" border style="width: 100%">
          <el-table-column prop="user_id" label="用户 ID" min-width="200" show-overflow-tooltip />
          <el-table-column prop="user_name" label="用户名" min-width="120" show-overflow-tooltip />
          <el-table-column label="角色" min-width="100">
            <template #default="{ row }">
              {{ row.role === 'leader' ? '群主' : '成员' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '有效 (active)' : row.status === 'left' ? '已退出 (left)' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="加入时间" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatDateTimeToCST(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="140" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openEditMember(row)">编辑</el-button>
              <el-button type="danger" link size="small" @click="handleDeleteMember(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="memberTotal > memberPageSize" class="admin-group-detail-pagination">
          <el-pagination
            v-model:current-page="memberPage"
            :page-size="memberPageSize"
            :total="memberTotal"
            layout="prev, pager, next"
            @current-change="fetchMemberships"
          />
        </div>
      </el-card>

      <!-- 历史会话卡 -->
      <el-card class="admin-group-detail-card" shadow="never">
        <h3 class="admin-group-detail-section-title">历史会话（{{ sessionTotal }} 条）</h3>
        <p v-if="sessions.length === 0 && !sessionLoading" class="admin-group-detail-empty">
          该群组暂无历史会话
        </p>
        <el-table v-else :data="sessions" v-loading="sessionLoading" border style="width: 100%">
          <el-table-column prop="id" label="会话 ID" min-width="200" show-overflow-tooltip />
          <el-table-column prop="session_title" label="标题" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" min-width="120">
            <template #default="{ row }">
              <el-tag :type="sessionStatusType(row.status)" size="small">
                {{ sessionStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatDateTimeToCST(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
        <div v-if="sessionTotal > sessionPageSize" class="admin-group-detail-pagination">
          <el-pagination
            v-model:current-page="sessionPage"
            :page-size="sessionPageSize"
            :total="sessionTotal"
            layout="prev, pager, next"
            @current-change="fetchSessions"
          />
        </div>
      </el-card>

      <!-- 危险操作卡 -->
      <el-card class="admin-group-detail-card admin-group-detail-danger" shadow="never">
        <h3 class="admin-group-detail-section-title admin-group-detail-danger-title">危险操作</h3>
        <div class="admin-group-detail-danger-actions">
          <div class="admin-group-detail-danger-item">
            <div>
              <p class="admin-group-detail-danger-label">
                {{ group?.is_active ? '停用群组' : '启用群组' }}
              </p>
              <p class="admin-group-detail-danger-desc">
                {{ group?.is_active ? '停用后该群组将不可发起新会话' : '重新启用后该群组可正常使用' }}
              </p>
            </div>
            <el-button
              :type="group?.is_active ? 'warning' : 'success'"
              size="small"
              @click="handleToggleActive"
            >
              {{ group?.is_active ? '停用群组' : '启用群组' }}
            </el-button>
          </div>
          <div class="admin-group-detail-danger-item">
            <div>
              <p class="admin-group-detail-danger-label">删除群组</p>
              <p class="admin-group-detail-danger-desc">删除后数据不可恢复，请谨慎操作</p>
            </div>
            <el-button type="danger" size="small" @click="handleDeleteGroup">删除群组</el-button>
          </div>
        </div>
      </el-card>
    </template>

    <!-- 编辑群组 dialog -->
    <el-dialog v-model="editGroupVisible" title="编辑群组" width="420px">
      <el-form ref="editGroupFormRef" :model="editGroupForm" :rules="editGroupRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="editGroupForm.name" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editGroupForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="editGroupVisible = false">取消</el-button>
          <el-button type="primary" @click="submitEditGroup">保存</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 编辑成员 dialog -->
    <el-dialog v-model="editMemberVisible" title="编辑成员关系" width="380px">
      <el-form :model="editMemberForm" label-width="80px">
        <el-form-item label="角色">
          <el-select v-model="editMemberForm.role" style="width: 100%">
            <el-option label="群主 (leader)" value="leader" />
            <el-option label="成员 (member)" value="member" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editMemberForm.status" style="width: 100%">
            <el-option label="有效 (active)" value="active" />
            <el-option label="已退出 (left)" value="left" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="editMemberVisible = false">取消</el-button>
          <el-button type="primary" @click="submitEditMember">保存</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-group-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-group-detail-nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-group-detail-nav-title {
  font-size: 14px;
  color: #6b7280;
}

.admin-group-detail-error {
  padding: 32px 16px;
  text-align: center;
}

.admin-group-detail-error-msg {
  margin: 0 0 16px;
  font-size: 14px;
  color: #ef4444;
}

.admin-group-detail-card {
  border-radius: 8px;
}

.admin-group-detail-info-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.admin-group-detail-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.admin-group-detail-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.admin-group-detail-meta {
  font-size: 12px;
  color: #6b7280;
  display: flex;
  gap: 4px;
  align-items: center;
}

.admin-group-detail-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.admin-group-detail-dot {
  color: #d1d5db;
}

.admin-group-detail-section-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.admin-group-detail-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.admin-group-detail-empty {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
}

.admin-group-detail-danger {
  border: 1px solid #fecaca;
}

.admin-group-detail-danger-title {
  color: #dc2626;
}

.admin-group-detail-danger-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.admin-group-detail-danger-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.admin-group-detail-danger-label {
  margin: 0 0 2px;
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.admin-group-detail-danger-desc {
  margin: 0;
  font-size: 12px;
  color: #6b7280;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
