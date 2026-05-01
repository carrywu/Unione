<template>
  <div class="page">
    <PageHeader>
      <template #actions>
        <el-button :icon="Back" @click="router.push('/banks')">返回题库</el-button>
      </template>
    </PageHeader>
    <div class="upload-shell">
      <aside class="flow-rail">
        <div class="flow-title">解析流程</div>
        <div class="flow-step" :class="{ active: activeStep === 0, done: activeStep > 0 }">
          <span>1</span>
          <div>
            <strong>选择题本</strong>
            <small>支持 PDF 拖拽上传</small>
          </div>
        </div>
        <div class="flow-step" :class="{ active: activeStep === 1 }">
          <span>2</span>
          <div>
            <strong>等待解析</strong>
            <small>自动轮询解析结果</small>
          </div>
        </div>
        <div class="flow-step" :class="{ active: task?.status === 'done' }">
          <span>3</span>
          <div>
            <strong>审核发布</strong>
            <small>检查题目与图片归属</small>
          </div>
        </div>
      </aside>

      <div class="panel upload-panel">
        <el-steps :active="activeStep" finish-status="success" align-center>
          <el-step title="上传 PDF" />
          <el-step title="解析进度" />
        </el-steps>

        <div v-if="activeStep === 0" class="step-body">
          <el-upload
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept="application/pdf"
            :on-change="handleFileChange"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-title">拖拽 PDF 到此处，或点击选择文件</div>
            <div class="upload-hint">上传后会进入解析队列，完成后可直接进入审核编辑。</div>
          </el-upload>
          <div v-if="selectedFile" class="file-row">
            <div class="file-name">
              <el-icon><Document /></el-icon>
              <span>{{ selectedFile.name }}</span>
            </div>
            <el-button type="primary" :icon="UploadFilled" :loading="uploading" @click="handleUpload">
              开始上传并解析
            </el-button>
          </div>
        </div>

        <div v-else class="step-body">
          <div class="progress-card">
            <div class="progress-head">
              <div>
                <strong>{{ statusText }}</strong>
                <span>{{ task?.file_name || selectedFile?.name || 'PDF 解析任务' }}</span>
              </div>
              <el-tag :type="statusType">{{ statusText }}</el-tag>
            </div>
            <el-progress :percentage="task?.progress || 0" :stroke-width="12" />
            <div class="status-line">
              <span v-if="task?.status === 'done'">完成题目数：{{ task.done_count }}</span>
              <span v-if="task?.status === 'failed'" class="error">{{ task.error }}</span>
              <span v-if="!task || task.status === 'pending' || task.status === 'processing'">请保持页面打开，系统会自动刷新。</span>
            </div>
          </div>
          <div v-if="task?.status === 'done'" class="done-actions">
            <el-button :icon="Document" type="primary" @click="router.push(`/banks/${bankId}/questions?taskId=${taskId}`)">
              查看解析题目
            </el-button>
            <el-button :icon="EditPen" type="success" @click="router.push(`/banks/${bankId}/review`)">
              进入审核编辑
            </el-button>
            <el-button :icon="Finished" type="warning" @click="router.push(`/banks/${bankId}/answer-book`)">
              上传解析册匹配答案
            </el-button>
          </div>

          <div v-if="task?.status === 'done'" class="result-section">
            <div class="result-head">
              <div>
                <h3>本次解析结果</h3>
                <p>先快速扫一遍，再进入审核页处理异常题。</p>
              </div>
              <el-button link type="primary" @click="fetchResultQuestions">刷新列表</el-button>
            </div>
            <el-table v-loading="resultLoading" :data="resultQuestions" row-key="id" border>
              <el-table-column prop="index_num" label="题号" width="80" />
              <el-table-column label="题干" min-width="280" show-overflow-tooltip>
                <template #default="{ row }">
                  <MathText :text="row.content" fallback="题干未能可靠定位" />
                </template>
              </el-table-column>
              <el-table-column prop="type" label="类型" width="90">
                <template #default="{ row }">{{ row.type === 'judge' ? '判断' : '单选' }}</template>
              </el-table-column>
              <el-table-column label="答案" width="80">
                <template #default="{ row }">
                  <MathText :text="row.answer" fallback="-" />
                </template>
              </el-table-column>
              <el-table-column label="状态" width="120">
                <template #default="{ row }">
                  <StatusTag :status="row.status" :needs-review="row.needs_review" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="router.push(`/banks/${bankId}/questions/${row.id}/preview`)">
                    PDF定位
                  </el-button>
                  <el-button link type="primary" @click="router.push(`/banks/${bankId}/review?questionId=${row.id}`)">
                    审核编辑
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UploadFile } from 'element-plus';
import { ElMessage } from 'element-plus';
import { computed, onBeforeUnmount, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Back, Document, EditPen, Finished, UploadFilled } from '@element-plus/icons-vue';
import { parsePdf, getTaskStatus, type ParseTask } from '@/api/pdf';
import { getQuestions, type Question } from '@/api/question';
import { uploadFile } from '@/api/upload';
import PageHeader from '@/components/PageHeader.vue';
import MathText from '@/components/MathText.vue';
import StatusTag from '@/components/StatusTag.vue';

const route = useRoute();
const router = useRouter();
const bankId = String(route.params.id);
const activeStep = ref(0);
const selectedFile = ref<File | null>(null);
const uploading = ref(false);
const taskId = ref('');
const task = ref<ParseTask | null>(null);
const resultLoading = ref(false);
const resultQuestions = ref<Question[]>([]);
let timer: number | undefined;

const statusText = computed(() => {
  const status = task.value?.status;
  if (status === 'pending') return '等待中';
  if (status === 'processing') return `解析中 ${task.value?.progress || 0}%`;
  if (status === 'done') return '完成';
  if (status === 'failed') return '失败';
  return '等待中';
});

const statusType = computed(() => {
  if (task.value?.status === 'done') return 'success';
  if (task.value?.status === 'failed') return 'danger';
  return 'warning';
});

function handleFileChange(uploadFileItem: UploadFile) {
  selectedFile.value = uploadFileItem.raw || null;
}

async function handleUpload() {
  if (!selectedFile.value) {
    ElMessage.warning('请选择 PDF 文件');
    return;
  }
  uploading.value = true;
  try {
    const uploaded = await uploadFile(selectedFile.value);
    const result = await parsePdf(bankId, uploaded.url);
    taskId.value = result.task_id;
    activeStep.value = 1;
    startPolling();
  } finally {
    uploading.value = false;
  }
}

function startPolling() {
  void fetchTask();
  timer = window.setInterval(fetchTask, 3000);
}

async function fetchTask() {
  if (!taskId.value) return;
  task.value = await getTaskStatus(taskId.value);
  if (task.value.status === 'done' || task.value.status === 'failed') {
    window.clearInterval(timer);
    if (task.value.status === 'done') {
      await fetchResultQuestions();
    }
  }
}

async function fetchResultQuestions() {
  if (!taskId.value) return;
  resultLoading.value = true;
  try {
    const result = await getQuestions({
      bankId,
      taskId: taskId.value,
      page: 1,
      pageSize: 200,
    });
    resultQuestions.value = result.list;
  } finally {
    resultLoading.value = false;
  }
}

onBeforeUnmount(() => window.clearInterval(timer));
</script>

<style scoped>
.upload-panel {
  padding: 24px;
}

.upload-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
}

.flow-rail {
  padding: 18px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
  box-shadow: var(--admin-shadow-sm);
}

.flow-title {
  margin-bottom: 14px;
  color: var(--admin-text);
  font-size: 16px;
  font-weight: 760;
}

.flow-step {
  display: flex;
  gap: 12px;
  padding: 14px 0;
  color: var(--admin-text-muted);
}

.flow-step + .flow-step {
  border-top: 1px solid var(--admin-border);
}

.flow-step span {
  display: grid;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--admin-border);
  border-radius: 999px;
  background: var(--admin-surface-soft);
  font-weight: 700;
}

.flow-step strong {
  display: block;
  color: var(--admin-text);
}

.flow-step small {
  display: block;
  margin-top: 4px;
  color: var(--admin-text-faint);
}

.flow-step.active span,
.flow-step.done span {
  border-color: var(--admin-accent);
  background: var(--admin-accent);
  color: oklch(98.5% 0.006 248);
}

.step-body {
  margin-top: 28px;
}

.upload-icon {
  margin-bottom: 12px;
  color: var(--admin-accent);
  font-size: 48px;
}

.upload-title {
  color: var(--admin-text);
  font-size: 16px;
  font-weight: 700;
}

.upload-hint {
  margin-top: 6px;
  color: var(--admin-text-faint);
  font-size: 13px;
}

.file-row,
.status-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}

.file-name {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
  color: var(--admin-text-muted);
}

.progress-card {
  padding: 18px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface-soft);
}

.progress-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.progress-head strong,
.progress-head span {
  display: block;
}

.progress-head strong {
  color: var(--admin-text);
  font-size: 18px;
}

.progress-head span {
  margin-top: 6px;
  color: var(--admin-text-faint);
  font-size: 13px;
}

.error {
  color: var(--admin-danger);
}

.done-actions {
  display: flex;
  gap: 12px;
  margin-top: 18px;
}

.result-section {
  margin-top: 24px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.result-head h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 740;
}

.result-head p {
  margin: 5px 0 0;
  color: var(--admin-text-faint);
  font-size: 13px;
}
</style>
