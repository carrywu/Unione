<template>
  <div class="page">
    <PageHeader />
    <div class="panel list-panel">
      <div class="toolbar">
        <el-select v-model="bankId" class="bank-select" clearable placeholder="全部题库" @change="fetchTasks">
          <el-option v-for="bank in banks" :key="bank.id" :label="bank.name" :value="bank.id" />
        </el-select>
        <el-button type="primary" @click="fetchTasks">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="tasks" row-key="id">
        <el-table-column prop="file_name" label="文件名" min-width="180" />
        <el-table-column label="题库" min-width="180">
          <template #default="{ row }">{{ row.bank?.name || row.bank_id }}</template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.task_type === 'answer_book' ? 'warning' : 'info'">
              {{ row.task_type === 'answer_book' ? '解析册' : '题本' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="180">
          <template #default="{ row }"><el-progress :percentage="row.progress || 0" /></template>
        </el-table-column>
        <el-table-column prop="done_count" label="题目数" width="90" />
        <el-table-column prop="attempt" label="重试" width="80" />
        <el-table-column label="诊断" min-width="220">
          <template #default="{ row }">
            <span v-if="row.error" class="task-error">{{ row.error }}</span>
            <span v-else-if="parseSummary(row).stats?.suspected_bad_parse" class="task-error">疑似解析失败</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openStatus(row)">查看状态</el-button>
            <el-button
              link
              type="primary"
              :disabled="row.status !== 'done'"
              @click="openResult(row)"
            >
              查看结果
            </el-button>
            <el-button
              link
              type="primary"
              :disabled="row.task_type !== 'answer_book'"
              @click="router.push(`/banks/${row.bank_id}/answer-book`)"
            >
              匹配页
            </el-button>
            <el-button
              v-if="canPublishResult(row)"
              link
              type="success"
              :loading="publishLoadingMap[row.id || '']"
              @click="handlePublishResult(row)"
            >
              一键发布结果
            </el-button>
            <el-button link type="warning" :disabled="!canPause(row.status)" @click="handlePause(row.id)">
              暂停
            </el-button>
            <el-button link type="primary" :disabled="!canRetry(row.status)" @click="handleRetry(row.id)">
              重试
            </el-button>
            <el-button link type="danger" :disabled="row.status === 'processing'" @click="handleDelete(row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="statusDrawerVisible" title="解析状态终端" size="560px" @closed="handleStatusDrawerClosed">
      <div v-if="selectedTask" class="terminal-wrap">
        <div class="terminal-toolbar">
          <el-tag :type="liveConnected ? 'success' : 'danger'">{{ liveConnected ? '实时连接中' : '连接断开' }}</el-tag>
          <el-tag :type="tagType(selectedTask.status)">{{ statusText(selectedTask.status) }}</el-tag>
          <span class="refresh-time">最后刷新：{{ lastLiveRefreshAt || '-' }}</span>
          <el-button size="small" :loading="statusRefreshing" @click="refreshSelectedTask">刷新</el-button>
          <el-button size="small" type="warning" :disabled="!canPause(selectedTask.status)" @click="handlePause(selectedTask.id)">
            暂停
          </el-button>
        </div>
        <pre class="terminal"><code>{{ terminalText }}</code></pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { getBanks, type Bank } from '@/api/bank';
import {
  deleteTask,
  getTaskList,
  getTaskStatus,
  pauseTask,
  publishParseResult,
  retryTask,
  type ParseTask,
} from '@/api/pdf';
import { pdfServiceApi, type PdfServiceStats, type PdfServiceStatus } from '@/api/pdf-service';
import PageHeader from '@/components/PageHeader.vue';

const router = useRouter();
const loading = ref(false);
const statusRefreshing = ref(false);
const bankId = ref('');
const banks = ref<Bank[]>([]);
const tasks = ref<ParseTask[]>([]);
const selectedTask = ref<ParseTask | null>(null);
const pdfStatus = ref<Partial<PdfServiceStatus>>({});
const pdfStats = ref<PdfServiceStats>({});
const statusDrawerVisible = ref(false);
const liveConnected = ref(false);
const lastLiveRefreshAt = ref('');
const terminalLines = ref<string[]>([]);
const publishLoadingMap = ref<Record<string, boolean>>({});
let refreshTimer: number | undefined;
let liveTimer: number | undefined;

const terminalText = computed(() => {
  const task = selectedTask.value;
  if (!task) return '';
  return [
    ...terminalLines.value,
    '',
    '$ live snapshot',
    `$ task ${task.id || '-'}`,
    `file: ${task.file_name || '-'}`,
    `bank: ${task.bank?.name || task.bank_id || '-'}`,
    `status: ${statusText(task.status)} (${task.status})`,
    `progress: ${task.progress || 0}%`,
    `questions: ${task.done_count || 0}/${task.total_count || 0}`,
    `attempt: ${task.attempt || 0}`,
    `created_at: ${formatTime(task.created_at)}`,
    `file_url: ${task.file_url || '-'}`,
    task.error ? `error: ${task.error}` : 'error: -',
    ...summaryTerminalLines(task),
    '',
    '# pdf-service',
    `reachable: ${pdfStatus.value.reachable ?? true}`,
    `service_status: ${pdfStatus.value.status || '-'}`,
    `queue: pending=${pdfStatus.value.queue?.pending ?? '-'} processing=${pdfStatus.value.queue?.processing ?? '-'} completed_today=${pdfStatus.value.queue?.completed_today ?? '-'}`,
    `memory_mb: ${pdfStatus.value.memory_mb ?? '-'}`,
    `qwen_last_call_at: ${pdfStatus.value.ai_providers?.qwen_vl?.last_call_at || '-'}`,
    `qwen_last_error: ${pdfStatus.value.ai_providers?.qwen_vl?.last_error || '-'}`,
    `deepseek_last_call_at: ${pdfStatus.value.ai_providers?.deepseek?.last_call_at || '-'}`,
    `session_ai_calls: ${JSON.stringify(pdfStats.value.session?.ai_calls || {})}`,
    '',
    hintLine(task),
  ].join('\n');
});

async function fetchTasks() {
  loading.value = true;
  try {
    tasks.value = await getTaskList(bankId.value);
    if (selectedTask.value?.id) {
      const latest = tasks.value.find((task) => task.id === selectedTask.value?.id);
      if (latest) selectedTask.value = latest;
    }
  } finally {
    loading.value = false;
  }
}

async function openStatus(task: ParseTask) {
  selectedTask.value = task;
  statusDrawerVisible.value = true;
  terminalLines.value = [];
  appendTerminal(`connect task ${task.id}`);
  startLiveStatus();
  await refreshSelectedTask();
}

async function refreshSelectedTask() {
  if (!selectedTask.value?.id) return;
  statusRefreshing.value = true;
  try {
    const before = selectedTask.value;
    const status = await getTaskStatus(selectedTask.value.id);
    selectedTask.value = { ...selectedTask.value, ...status };
    await fetchPdfRuntime();
    await fetchTasks();
    liveConnected.value = true;
    lastLiveRefreshAt.value = new Date().toLocaleTimeString();
    appendTerminal(formatTaskDelta(before, selectedTask.value));
  } catch (error) {
    liveConnected.value = false;
    lastLiveRefreshAt.value = new Date().toLocaleTimeString();
    appendTerminal(`error ${error instanceof Error ? error.message : 'refresh failed'}`);
  } finally {
    statusRefreshing.value = false;
  }
}

function startLiveStatus() {
  stopLiveStatus();
  liveConnected.value = true;
  liveTimer = window.setInterval(() => {
    if (statusDrawerVisible.value) void refreshSelectedTask();
  }, 2000);
}

function stopLiveStatus() {
  if (liveTimer) window.clearInterval(liveTimer);
  liveTimer = undefined;
  liveConnected.value = false;
}

function appendTerminal(line: string) {
  terminalLines.value.push(`[${new Date().toLocaleTimeString()}] ${line}`);
  if (terminalLines.value.length > 120) terminalLines.value = terminalLines.value.slice(-120);
}

function formatTaskDelta(before: ParseTask, after: ParseTask) {
  const parts = [
    `status=${after.status}`,
    `progress=${after.progress || 0}%`,
    `questions=${after.done_count || 0}/${after.total_count || 0}`,
  ];
  const pdfQueue = pdfStatus.value.queue;
  if (pdfQueue) parts.push(`pdf_queue=p${pdfQueue.pending}/r${pdfQueue.processing}/d${pdfQueue.completed_today}`);
  const lastCall = pdfStatus.value.ai_providers?.qwen_vl?.last_call_at;
  if (lastCall) parts.push(`qwen_last=${new Date(lastCall).toLocaleTimeString()}`);
  if (before.status !== after.status) parts.push(`changed ${before.status}->${after.status}`);
  return parts.join(' ');
}

function parseSummary(task: ParseTask | null) {
  if (!task?.result_summary) return {};
  try {
    return JSON.parse(task.result_summary) as Record<string, any>;
  } catch {
    return { raw: task.result_summary };
  }
}

function summaryTerminalLines(task: ParseTask) {
  const summary = parseSummary(task);
  const stats = summary.stats || {};
  const counts = stats.debug_counts || {};
  const warnings = summary.warnings || stats.warnings || [];
  return [
    '',
    '# parse summary',
    `suspected_bad_parse: ${stats.suspected_bad_parse ?? false}`,
    `warnings: ${Array.isArray(warnings) ? warnings.join(', ') || '-' : String(warnings)}`,
    `pages_count: ${counts.pages_count ?? '-'}`,
    `page_elements_count: ${counts.page_elements_count ?? '-'}`,
    `question_candidates_count: ${counts.question_candidates_count ?? '-'}`,
    `accepted_questions_count: ${counts.accepted_questions_count ?? '-'}`,
    `rejected_questions_count: ${counts.rejected_questions_count ?? '-'}`,
    `materials_count: ${counts.materials_count ?? '-'}`,
    `visuals_count: ${counts.visuals_count ?? '-'}`,
    `detection: ${JSON.stringify(summary.detection || stats.detection || {})}`,
    stats.scanned_fallback_debug ? `scanned_fallback_debug: ${JSON.stringify(stats.scanned_fallback_debug)}` : 'scanned_fallback_debug: -',
  ];
}

function handleStatusDrawerClosed() {
  stopLiveStatus();
  selectedTask.value = null;
}

async function fetchPdfRuntime() {
  try {
    const [status, stats] = await Promise.all([pdfServiceApi.getStatus(), pdfServiceApi.getStats()]);
    pdfStatus.value = status;
    pdfStats.value = stats;
  } catch (error) {
    pdfStatus.value = { status: 'offline', reachable: false, error: error instanceof Error ? error.message : 'PDF 服务不可达' };
    pdfStats.value = {};
  }
}

async function handleRetry(id?: string) {
  if (!id) return;
  await retryTask(id);
  ElMessage.success('已重新提交解析');
  await fetchTasks();
}

async function handlePause(id?: string) {
  if (!id) return;
  await ElMessageBox.confirm('确认暂停该解析任务？暂停后可点击重试重新开始。', '暂停解析', { type: 'warning' });
  await pauseTask(id);
  ElMessage.success('已暂停解析');
  await fetchTasks();
  if (selectedTask.value?.id === id) await refreshSelectedTask();
}

async function handlePublishResult(task: ParseTask) {
  if (!task.id || !canPublishResult(task)) return;
  await ElMessageBox.confirm(
    '将发布本次解析入库的题目，并发布题库，H5 将可见。是否继续？',
    '发布解析结果',
    { type: 'warning' },
  );

  publishLoadingMap.value = { ...publishLoadingMap.value, [task.id]: true };
  try {
    const result = await publishParseResult(task.id, { publish_bank: true });
    ElMessage.success(
      `已发布 ${result.published_count} 题，题库状态 ${result.bank_status}，总题数 ${result.total_count}`,
    );
    await fetchTasks();
    if (selectedTask.value?.id === task.id) await refreshSelectedTask();
  } finally {
    publishLoadingMap.value = { ...publishLoadingMap.value, [task.id]: false };
  }
}

async function handleDelete(id?: string) {
  if (!id) return;
  await ElMessageBox.confirm('确认删除该任务记录？', '删除任务', { type: 'warning' });
  await deleteTask(id);
  ElMessage.success('已删除');
  await fetchTasks();
}

function statusText(status: string) {
  return { pending: '等待中', processing: '解析中', done: '完成', failed: '失败', paused: '已暂停' }[status] || status;
}

function tagType(status: string) {
  if (status === 'done') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'paused') return 'info';
  return 'warning';
}

function canPause(status: string) {
  return ['pending', 'processing'].includes(status);
}

function canRetry(status: string) {
  return ['failed', 'paused'].includes(status);
}

function canPublishResult(task: ParseTask) {
  return task.status === 'done' && task.task_type !== 'answer_book';
}

function openResult(task: ParseTask) {
  if (task.task_type === 'answer_book') {
    void router.push(`/banks/${task.bank_id}/answer-book`);
    return;
  }
  void router.push(`/banks/${task.bank_id}/questions?taskId=${task.id}`);
}

function formatTime(value?: string) {
  return value ? new Date(value).toLocaleString() : '-';
}

function hintLine(task: ParseTask) {
  if (task.status === 'processing' && (task.progress || 0) <= 10 && !(task.done_count || 0)) {
    return 'hint: 仍在 PDF 服务解析阶段；如长时间无变化，可先暂停再重试。';
  }
  if (task.status === 'paused') return 'hint: 任务已暂停，可重试重新开始解析。';
  if (task.status === 'failed' && task.error === '未解析到题目') return 'hint: 未解析到题目，请查看 parse summary 后重试或人工框选。';
  if (task.status === 'failed') return 'hint: 任务失败，可查看 error 后重试。';
  if (task.status === 'done') return 'hint: 解析完成，可点击查看结果。';
  return 'hint: 等待解析调度。';
}

onMounted(async () => {
  banks.value = (await getBanks({ page: 1, pageSize: 100 })).list;
  await fetchTasks();
  await fetchPdfRuntime();
  refreshTimer = window.setInterval(async () => {
    await fetchTasks();
    if (statusDrawerVisible.value) await fetchPdfRuntime();
  }, 5000);
});

onBeforeUnmount(() => {
  window.clearInterval(refreshTimer);
  stopLiveStatus();
});
</script>

<style scoped>
.list-panel {
  padding: 16px;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.bank-select {
  width: 280px;
}

.terminal-wrap {
  display: grid;
  gap: 12px;
}

.terminal-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.refresh-time {
  color: #6b7280;
  font-size: 12px;
}

.terminal {
  min-height: 360px;
  padding: 14px;
  border-radius: 10px;
  overflow: auto;
  background: #111827;
  color: #d1fae5;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.task-error {
  color: #b91c1c;
}

.muted {
  color: #94a3b8;
}
</style>
