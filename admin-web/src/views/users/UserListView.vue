<template>
  <div class="page">
    <PageHeader />
    <div class="panel list-panel">
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          class="search"
          clearable
          placeholder="搜索手机号或昵称"
          @keyup.enter="fetchUsers"
          @clear="fetchUsers"
        />
        <el-select v-model="query.role" class="role-select" clearable placeholder="全部角色" @change="fetchUsers">
          <el-option label="管理员" value="admin" />
          <el-option label="普通用户" value="user" />
        </el-select>
        <el-button type="primary" @click="fetchUsers">搜索</el-button>
      </div>

      <el-table v-loading="loading" :data="users" row-key="id">
        <el-table-column prop="phone" label="手机号" width="160" />
        <el-table-column prop="nickname" label="昵称" min-width="180" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最近登录" width="190">
          <template #default="{ row }">{{ formatTime(row.last_login_at) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="190">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="openDetail(row)">记录</el-button>
            <el-button link type="warning" @click="handleResetPassword(row)">重置密码</el-button>
            <el-button link :type="row.is_active ? 'warning' : 'success'" @click="handleToggle(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.pageSize"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchUsers"
          @size-change="fetchUsers"
        />
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="编辑用户" width="460px">
      <el-form :model="form" label-position="top">
        <el-form-item label="手机号">
          <el-input v-model="form.phone" disabled />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" />
        </el-form-item>
        <el-form-item label="头像">
          <el-input v-model="form.avatar" placeholder="头像 URL" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" class="full">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="用户学习情况" width="860px">
      <div class="stats-row">
        <el-statistic title="总答题" :value="Number(userStats.total_answered || 0)" />
        <el-statistic title="正确数" :value="Number(userStats.correct_count || 0)" />
        <el-statistic title="正确率" :value="Number(userStats.accuracy_rate || 0)" suffix="%" />
        <el-statistic title="连续天数" :value="Number(userStats.streak_days || 0)" />
      </div>
      <el-table :data="records" size="small" max-height="360">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="题目" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <MathText :text="row.question?.content" fallback="题干未能可靠定位" />
          </template>
        </el-table-column>
        <el-table-column prop="user_answer" label="作答" width="80" />
        <el-table-column prop="is_correct" label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_correct ? 'success' : 'danger'">{{ row.is_correct ? '正确' : '错误' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="question.bank.name" label="题库" min-width="160" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';
import {
  deleteUser,
  getUserRecords,
  getUserStats,
  getUsers,
  resetUserPassword,
  toggleUserActive,
  updateUser,
  type AdminUser,
} from '@/api/user';
import PageHeader from '@/components/PageHeader.vue';
import MathText from '@/components/MathText.vue';

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const detailVisible = ref(false);
const users = ref<AdminUser[]>([]);
const records = ref<any[]>([]);
const userStats = ref<Record<string, unknown>>({});
const total = ref(0);
const query = reactive({
  page: 1,
  pageSize: 10,
  keyword: '',
  role: '',
});
const form = reactive<Partial<AdminUser>>({});

async function fetchUsers() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: query.page,
      pageSize: query.pageSize,
    };
    if (query.keyword) params.keyword = query.keyword;
    if (query.role) params.role = query.role;
    const result = await getUsers(params);
    users.value = result.list;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

function openEdit(user: AdminUser) {
  Object.keys(form).forEach((key) => delete form[key as keyof AdminUser]);
  Object.assign(form, user);
  dialogVisible.value = true;
}

async function handleSave() {
  if (!form.id) return;
  saving.value = true;
  try {
    await updateUser(form.id, {
      nickname: form.nickname,
      avatar: form.avatar,
      role: form.role,
    });
    ElMessage.success('已保存');
    dialogVisible.value = false;
    await fetchUsers();
  } finally {
    saving.value = false;
  }
}

async function handleDelete(user: AdminUser) {
  await ElMessageBox.confirm(`确认删除用户 ${user.phone}？`, '删除用户', {
    type: 'warning',
  });
  await deleteUser(user.id);
  ElMessage.success('已删除');
  await fetchUsers();
}

async function handleToggle(user: AdminUser) {
  const action = user.is_active ? '禁用' : '启用';
  await ElMessageBox.confirm(`确认${action}用户 ${user.phone}？`, `${action}用户`, {
    type: 'warning',
  });
  const result = await toggleUserActive(user.id);
  ElMessage.success(result.message);
  await fetchUsers();
}

async function handleResetPassword(user: AdminUser) {
  const { value } = await ElMessageBox.prompt('请输入新密码（6-20位）', `重置 ${user.phone} 密码`, {
    inputPattern: /^[a-zA-Z0-9!@#$%^&*]{6,20}$/,
    inputErrorMessage: '密码格式不正确',
  });
  await resetUserPassword(user.id, value);
  ElMessage.success('密码已重置');
}

async function openDetail(user: AdminUser) {
  const [stats, recordResult] = await Promise.all([
    getUserStats(user.id),
    getUserRecords(user.id, { page: 1, pageSize: 20 }),
  ]);
  userStats.value = stats;
  records.value = (recordResult as any).list || [];
  detailVisible.value = true;
}

function formatTime(value?: string) {
  return value ? new Date(value).toLocaleString() : '';
}

onMounted(fetchUsers);
</script>

<style scoped>
.list-panel {
  padding: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.search {
  width: 260px;
}

.role-select {
  width: 140px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.full {
  width: 100%;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
</style>
