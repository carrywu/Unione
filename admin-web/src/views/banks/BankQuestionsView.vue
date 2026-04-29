<template>
  <div class="page">
    <PageHeader />
    <div class="panel list-panel">
      <div class="toolbar">
        <el-button type="primary" @click="router.push(`/banks/${bankId}/review`)">进入审核</el-button>
        <el-tag v-if="taskId" type="info" closable @close="clearTaskFilter">仅显示本次解析结果</el-tag>
        <el-checkbox v-model="query.needsReview" label="仅待审核" @change="fetchQuestions" />
      </div>
      <el-alert
        v-if="taskId && !loading && !questions.length"
        class="empty-result-alert"
        type="warning"
        :closable="false"
        show-icon
        title="未解析到题目"
      >
        <template #default>
          <div class="empty-result-actions">
            <span>请查看解析日志，或重试该任务；也可以进入题干审核工作台人工框选。</span>
            <el-button size="small" type="primary" @click="router.push('/pdf/tasks')">查看解析日志</el-button>
            <el-button size="small" :loading="retrying" :disabled="!taskStatus || taskStatus.status === 'processing'" @click="handleRetryTask">
              重试
            </el-button>
            <el-button size="small" @click="router.push(`/workbench?bankId=${bankId}`)">人工框选</el-button>
          </div>
        </template>
      </el-alert>
      <el-table v-loading="loading" :data="questions" row-key="id">
        <template #empty>
          <el-empty description="未解析到题目，请查看解析日志/重试/人工框选" />
        </template>
        <el-table-column prop="index_num" label="题号" width="90" />
        <el-table-column prop="content" label="题干" min-width="360" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <StatusTag :status="row.status" :needs-review="row.needs_review" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/banks/${bankId}/questions/${row.id}/preview`)">
              PDF定位
            </el-button>
            <el-button link type="primary" @click="router.push(`/banks/${bankId}/review?questionId=${row.id}`)">
              编辑
            </el-button>
            <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchQuestions"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getTaskStatus, retryTask, type ParseTask } from '@/api/pdf';
import { deleteQuestion, getQuestions, type Question } from '@/api/question';
import PageHeader from '@/components/PageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';

const route = useRoute();
const router = useRouter();
const bankId = String(route.params.id);
const taskId = ref(String(route.query.taskId || ''));
const loading = ref(false);
const retrying = ref(false);
const questions = ref<Question[]>([]);
const total = ref(0);
const taskStatus = ref<ParseTask | null>(null);
const query = reactive({
  bankId,
  page: 1,
  pageSize: 20,
  needsReview: false,
});

async function fetchQuestions() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      bankId: query.bankId,
      page: query.page,
      pageSize: query.pageSize,
    };
    if (query.needsReview) params.needsReview = true;
    if (taskId.value) params.taskId = taskId.value;
    const result = await getQuestions(params);
    questions.value = result.list;
    total.value = result.total;
    taskStatus.value = taskId.value ? await getTaskStatus(taskId.value) : null;
  } finally {
    loading.value = false;
  }
}

async function handleRetryTask() {
  if (!taskId.value) return;
  retrying.value = true;
  try {
    await retryTask(taskId.value);
    ElMessage.success('已重新提交解析');
    await fetchQuestions();
  } finally {
    retrying.value = false;
  }
}

async function clearTaskFilter() {
  taskId.value = '';
  await router.replace(`/banks/${bankId}/questions`);
  await fetchQuestions();
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm('确认删除该题目？', '删除题目', { type: 'warning' });
  await deleteQuestion(id);
  ElMessage.success('已删除');
  await fetchQuestions();
}

onMounted(fetchQuestions);
</script>

<style scoped>
.list-panel {
  padding: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.empty-result-alert {
  margin-bottom: 14px;
}

.empty-result-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
