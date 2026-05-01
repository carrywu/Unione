<template>
  <div class="page answer-book-page">
    <PageHeader />

    <div class="match-layout">
      <section class="panel setup-panel">
        <div class="section-head">
          <div>
            <h2>题册与解析册</h2>
            <p>题本负责题目，解析册负责答案与解析，匹配后写回题目。</p>
          </div>
          <el-button @click="router.push(`/banks/${bankId}/questions`)">查看题目</el-button>
        </div>

        <div class="summary-grid">
          <div class="summary-item">
            <span>题目数</span>
            <strong>{{ questionTotal }}</strong>
          </div>
          <div class="summary-item">
            <span>答案源</span>
            <strong>{{ answerSources.length }}</strong>
          </div>
          <div class="summary-item">
            <span>已匹配</span>
            <strong>{{ sourceStats.matched }}</strong>
          </div>
          <div class="summary-item">
            <span>待处理</span>
            <strong>{{ sourceStats.unmatched + sourceStats.ambiguous }}</strong>
          </div>
        </div>

        <el-divider />

        <el-form label-position="top">
          <el-form-item label="解析册类型">
            <el-radio-group v-model="mode">
              <el-radio-button label="text">文字解析册</el-radio-button>
              <el-radio-button label="image">图片/笔记解析册</el-radio-button>
              <el-radio-button label="auto">自动识别</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-upload
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept="application/pdf"
            :on-change="handleFileChange"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>上传答案解析册 PDF</div>
          </el-upload>

          <div v-if="selectedFile" class="file-row">
            <span>{{ selectedFile.name }}</span>
            <el-button type="primary" :loading="uploading" @click="handleUpload">
              上传并解析匹配
            </el-button>
          </div>
        </el-form>

        <div v-if="taskId" class="task-box">
          <div class="task-title">
            <span>当前解析册任务</span>
            <el-tag :type="taskTagType">{{ taskStatusText }}</el-tag>
          </div>
          <el-progress :percentage="task?.progress || 0" />
          <div class="task-actions">
            <span v-if="task?.status === 'done'">答案源 {{ task.done_count }} 条</span>
            <span v-if="task?.status === 'failed'" class="error">{{ task.error }}</span>
            <el-button
              size="small"
              type="primary"
              :disabled="task?.status !== 'done'"
              :loading="matching"
              @click="handleRematch"
            >
              重新匹配
            </el-button>
          </div>
        </div>

        <el-alert
          v-if="matchNotice"
          class="match-notice"
          :title="matchNotice.title"
          :description="matchNotice.description"
          :type="matchNotice.type"
          :closable="false"
          show-icon
        />
      </section>

      <section class="panel sources-panel">
        <div class="section-head compact">
          <div>
            <h2>答案源对比</h2>
            <p>按题号展示解析册输出与题本匹配结果。</p>
          </div>
          <div class="filters">
            <el-select v-model="statusFilter" clearable placeholder="全部状态" @change="fetchSources">
              <el-option label="已匹配" value="matched" />
              <el-option label="待匹配" value="unmatched" />
              <el-option label="需确认" value="ambiguous" />
              <el-option label="冲突" value="conflict" />
              <el-option label="已忽略" value="ignored" />
            </el-select>
            <el-button :loading="sourcesLoading" @click="refreshAll">刷新</el-button>
          </div>
        </div>

        <el-alert
          v-if="listNotice"
          class="list-notice"
          :title="listNotice.title"
          :description="listNotice.description"
          :type="listNotice.type"
          :closable="false"
          show-icon
        />

        <el-table v-loading="sourcesLoading" :data="answerSources" row-key="id" border>
          <el-table-column prop="question_index" label="题号" width="80" />
          <el-table-column label="解析册内容" min-width="260">
            <template #default="{ row }">
              <div class="source-main">
                <div class="source-line">
                  <el-tag size="small" :type="row.parse_mode === 'image' ? 'warning' : 'info'">
                    {{ row.parse_mode === 'image' ? '图片' : '文字' }}
                  </el-tag>
                  <strong v-if="row.answer">答案 <MathText :text="row.answer" /></strong>
                  <span>第 {{ row.source_page_num }} 页</span>
                </div>
                <p v-if="row.analysis_text" class="analysis-snippet"><MathText :text="row.analysis_text" /></p>
                <ImagePreview v-if="row.analysis_image_url" class="analysis-preview" :src="row.analysis_image_url" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="题本匹配" min-width="260">
            <template #default="{ row }">
              <div v-if="row.matched_question" class="question-match">
                <div class="source-line">
                  <el-tag size="small" type="success">第 {{ row.matched_question.index_num }} 题</el-tag>
                  <span>置信度 {{ row.match_score ?? '-' }}</span>
                </div>
                <p><MathText :text="row.matched_question.content" fallback="题干未能可靠定位" /></p>
              </div>
              <el-empty v-else description="未绑定题目" :image-size="48" />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="sourceStatusType(row.status)">{{ sourceStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="!row.matched_question_id"
                @click="router.push(`/banks/${bankId}/questions/${row.matched_question_id}/preview`)"
              >
                看题目
              </el-button>
              <el-button
                v-if="row.status === 'matched'"
                link
                type="warning"
                @click="handleUnbind(row.id)"
              >
                解绑
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="!sourcesLoading && !answerSources.length" :description="emptyDescription" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UploadFile } from 'element-plus';
import { ElMessage } from 'element-plus';
import { UploadFilled } from '@element-plus/icons-vue';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  createAnswerBookTask,
  getAnswerSources,
  matchAnswerBookTask,
  unbindAnswerSource,
  type AnswerBookMode,
  type AnswerSource,
  type AnswerSourceStatus,
} from '@/api/answer-book';
import { getTaskStatus, type ParseTask } from '@/api/pdf';
import { getQuestions } from '@/api/question';
import { uploadFile } from '@/api/upload';
import ImagePreview from '@/components/ImagePreview.vue';
import MathText from '@/components/MathText.vue';
import PageHeader from '@/components/PageHeader.vue';

const route = useRoute();
const router = useRouter();
const bankId = String(route.params.id);
const mode = ref<AnswerBookMode>('auto');
const selectedFile = ref<File | null>(null);
const uploading = ref(false);
const matching = ref(false);
const taskId = ref('');
const task = ref<ParseTask | null>(null);
const questionTotal = ref(0);
const sourcesLoading = ref(false);
const answerSources = ref<AnswerSource[]>([]);
const statusFilter = ref<AnswerSourceStatus | ''>('');
let timer: number | undefined;

const sourceStats = computed(() => ({
  matched: answerSources.value.filter((item) => item.status === 'matched').length,
  ambiguous: answerSources.value.filter((item) => item.status === 'ambiguous').length,
  unmatched: answerSources.value.filter((item) => item.status === 'unmatched').length,
}));

const taskSummary = computed(() => {
  if (!task.value?.result_summary) return null;
  try {
    return JSON.parse(task.value.result_summary) as {
      total?: number;
      matched?: number;
      ambiguous?: number;
      unmatched?: number;
      ignored?: number;
      parsed_total?: number;
    };
  } catch {
    return null;
  }
});

const effectiveStats = computed(() => ({
  total: taskSummary.value?.total ?? answerSources.value.length,
  matched: taskSummary.value?.matched ?? sourceStats.value.matched,
  ambiguous: taskSummary.value?.ambiguous ?? sourceStats.value.ambiguous,
  unmatched: taskSummary.value?.unmatched ?? sourceStats.value.unmatched,
}));

const matchNotice = computed(() => {
  if (task.value?.status === 'failed') {
    return {
      type: 'error' as const,
      title: '解析失败',
      description: task.value.error || 'PDF 服务没有返回可用结果，请检查服务状态或重新上传文件。',
    };
  }
  if (task.value?.status !== 'done') return null;

  const stats = effectiveStats.value;
  if (stats.total > 0 && stats.matched === 0 && stats.ambiguous + stats.unmatched > 0) {
    return {
      type: 'warning' as const,
      title: '未自动匹配到题目',
      description:
        '解析册内容与题本缺少可靠文本重叠，系统已停止写回题目。请确认是否上传了当前题库对应的解析册；如确认为同一套资料，可在“需确认”中人工核对后绑定。',
    };
  }
  if (stats.matched > 0 && stats.ambiguous + stats.unmatched > 0) {
    return {
      type: 'warning' as const,
      title: '部分答案源需要处理',
      description: `已自动匹配 ${stats.matched} 条，仍有 ${
        stats.ambiguous + stats.unmatched
      } 条缺少足够证据，需要人工确认或重新上传对应解析册。`,
    };
  }
  return null;
});

const listNotice = computed(() => {
  if (matchNotice.value) return matchNotice.value;
  if (!taskId.value && answerSources.value.length > 0 && sourceStats.value.matched === 0) {
    return {
      type: 'warning' as const,
      title: '当前没有已匹配答案源',
      description: '列表中的答案源尚未写回题目。请优先检查解析册是否属于当前题库，再进行人工绑定。',
    };
  }
  return null;
});

const emptyDescription = computed(() => {
  if (statusFilter.value) return `没有${sourceStatusText(statusFilter.value)}的答案源`;
  if (task.value?.status === 'done') return '本次解析没有可展示的答案源，请确认 PDF 内容或重新上传';
  return '还没有答案源，先上传解析册';
});

const taskStatusText = computed(() => {
  if (!task.value) return '等待上传';
  return { pending: '等待中', processing: '解析中', done: '完成', failed: '失败', paused: '已暂停' }[
    task.value.status
  ] || task.value.status;
});

const taskTagType = computed(() => {
  if (task.value?.status === 'done') return 'success';
  if (task.value?.status === 'failed') return 'danger';
  if (task.value?.status === 'paused') return 'info';
  return 'warning';
});

function handleFileChange(uploadFileItem: UploadFile) {
  selectedFile.value = uploadFileItem.raw || null;
}

async function handleUpload() {
  if (!selectedFile.value) {
    ElMessage.warning('请选择答案解析册 PDF');
    return;
  }
  uploading.value = true;
  try {
    const uploaded = await uploadFile(selectedFile.value);
    const result = await createAnswerBookTask(bankId, {
      file_url: uploaded.url,
      file_name: uploaded.filename,
      mode: mode.value,
    });
    taskId.value = result.task_id;
    task.value = null;
    ElMessage.success('已提交答案册解析');
    startPolling();
  } finally {
    uploading.value = false;
  }
}

function startPolling() {
  stopPolling();
  void fetchTask();
  timer = window.setInterval(fetchTask, 3000);
}

function stopPolling() {
  if (timer) window.clearInterval(timer);
  timer = undefined;
}

async function fetchTask() {
  if (!taskId.value) return;
  task.value = await getTaskStatus(taskId.value);
  if (['done', 'failed', 'paused'].includes(task.value.status)) {
    stopPolling();
    await fetchSources();
  }
}

async function fetchQuestionTotal() {
  const result = await getQuestions({ bankId, page: 1, pageSize: 1 });
  questionTotal.value = result.total;
}

async function fetchSources() {
  sourcesLoading.value = true;
  try {
    answerSources.value = await getAnswerSources({
      bank_id: bankId,
      status: statusFilter.value,
    });
  } finally {
    sourcesLoading.value = false;
  }
}

async function refreshAll() {
  await Promise.all([fetchQuestionTotal(), fetchSources()]);
  if (taskId.value) await fetchTask();
}

async function handleRematch() {
  if (!taskId.value) return;
  matching.value = true;
  try {
    const result = await matchAnswerBookTask(taskId.value);
    ElMessage.success(
      `已匹配 ${result.matched} 条，待处理 ${result.ambiguous + result.unmatched} 条，忽略 ${result.ignored || 0} 条`,
    );
    await fetchSources();
  } finally {
    matching.value = false;
  }
}

async function handleUnbind(sourceId: string) {
  await unbindAnswerSource(sourceId);
  ElMessage.success('已解绑');
  await fetchSources();
}

function sourceStatusText(status: string) {
  return { matched: '已匹配', unmatched: '待匹配', ambiguous: '需确认', conflict: '冲突', ignored: '已忽略' }[
    status
  ] || status;
}

function sourceStatusType(status: string) {
  if (status === 'matched') return 'success';
  if (status === 'ambiguous') return 'warning';
  if (status === 'conflict') return 'danger';
  if (status === 'ignored') return 'info';
  return 'info';
}

onMounted(refreshAll);
onBeforeUnmount(stopPolling);
</script>

<style scoped>
.match-layout {
  display: grid;
  grid-template-columns: minmax(360px, 420px) minmax(0, 1fr);
  gap: 16px;
}

.setup-panel,
.sources-panel {
  padding: 20px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.section-head.compact {
  align-items: center;
}

.section-head h2 {
  margin: 0 0 6px;
  color: #111827;
  font-size: 18px;
  font-weight: 700;
}

.section-head p {
  margin: 0;
  color: #6b7280;
  font-size: 13px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.summary-item {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
}

.summary-item span {
  display: block;
  color: #6b7280;
  font-size: 12px;
}

.summary-item strong {
  display: block;
  margin-top: 4px;
  color: #111827;
  font-size: 22px;
}

.upload-icon {
  margin-bottom: 10px;
  color: #909399;
  font-size: 42px;
}

.file-row,
.task-title,
.task-actions,
.source-line,
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-row {
  justify-content: space-between;
  margin-top: 12px;
}

.task-box {
  margin-top: 18px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
}

.match-notice,
.list-notice {
  margin-top: 14px;
}

.list-notice {
  margin-bottom: 14px;
}

.task-title,
.task-actions {
  justify-content: space-between;
}

.task-title {
  margin-bottom: 10px;
  font-weight: 650;
}

.task-actions {
  margin-top: 10px;
  color: #6b7280;
  font-size: 13px;
}

.source-main,
.question-match {
  display: grid;
  gap: 8px;
}

.source-line {
  flex-wrap: wrap;
  color: #6b7280;
  font-size: 12px;
}

.analysis-snippet,
.question-match p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: #374151;
  font-size: 13px;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.analysis-preview {
  max-width: 220px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.error {
  color: #f56c6c;
}

@media (max-width: 1100px) {
  .match-layout {
    grid-template-columns: 1fr;
  }
}
</style>
