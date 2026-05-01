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
              @click="openAiPreaudit(row)"
            >
              AI预审核
            </el-button>
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
              type="success"
              :disabled="row.status !== 'done' || row.task_type === 'answer_book'"
              @click="openPaperReview(row)"
            >
              制卷核对
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

    <el-drawer v-model="aiDrawerVisible" title="AI预审核证据" size="680px">
      <div v-if="aiDebugLoading" class="ai-debug-loading">加载中...</div>
      <div v-else-if="aiDebugError" class="ai-debug-error">{{ aiDebugError }}</div>
      <div v-else-if="aiDebug" class="ai-debug">
        <el-alert
          :title="aiDebugHeadline"
          :type="aiDebugHasFailure ? 'warning' : 'success'"
          show-icon
          :closable="false"
        />
        <div class="ai-debug-grid">
          <div>
            <span>taskId</span>
            <strong>{{ aiDebug.taskId }}</strong>
          </div>
          <div>
            <span>bankId</span>
            <strong>{{ aiDebug.bankId }}</strong>
          </div>
          <div>
            <span>vision_ai</span>
            <strong>{{ aiDebug.qwen_vl_enabled ? `called ${aiDebug.qwen_vl_call_count}` : 'not called' }}</strong>
          </div>
        </div>
        <div v-for="row in aiPreviewRows" :key="row.key" class="ai-debug-card">
          <div class="ai-debug-card-head">
            <strong>{{ row.label }}</strong>
            <el-tag :type="row.status === 'failed' ? 'danger' : row.status === 'warning' ? 'warning' : 'success'">
              {{ row.statusText }}
            </el-tag>
            <el-tag v-if="row.needManualFix" type="warning">need_manual_fix</el-tag>
          </div>
          <p><span>题干</span><MathText :text="row.stem" fallback="题干未能可靠定位" /></p>
          <p><span>图表</span>{{ row.visualSummary }}</p>
          <p><span>预览</span>{{ row.preview }}</p>
          <p><span>答案</span><MathText :text="row.answer" fallback="未给出答案建议" /></p>
          <div class="risk-tags">
            <el-tag v-for="flag in row.riskFlags" :key="flag" size="small" type="warning">
              {{ flag }}
            </el-tag>
          </div>
        </div>
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
  getAiPreauditDebug,
  getTaskList,
  getTaskStatus,
  pauseTask,
  publishParseResult,
  retryTask,
  type AiPreauditDebug,
  type ParseTask,
} from '@/api/pdf';
import { pdfServiceApi, type PdfServiceStats, type PdfServiceStatus } from '@/api/pdf-service';
import MathText from '@/components/MathText.vue';
import PageHeader from '@/components/PageHeader.vue';
import { mathTextToString } from '@/utils/mathText';

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
const aiDrawerVisible = ref(false);
const aiDebugLoading = ref(false);
const aiDebugError = ref('');
const aiDebug = ref<AiPreauditDebug | null>(null);
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

const aiPreviewRows = computed(() => {
  const previewQuestions = aiDebug.value?.final_preview_payload?.questions || [];
  const audits = aiDebug.value?.ai_audit_results || [];
  return previewQuestions.map((question, index) => {
    const audit = audits[index] || {};
    const riskFlags = normalizeStringList(audit.risk_flags || question.risk_flags);
    const status = String(audit.ai_audit_status || question.ai_audit_status || question.visual_parse_status || 'unknown');
    const questionNo = question.question_no ?? audit.question_no;
    const visualSummary = stringValue(question.visual_summary || audit.ai_audit_summary, '图表预览不可用：视觉模型未返回结构化结果');
    const previewPath = stringValue(question.preview_image_path, '图表预览不可用：仅保留失败原因与源 artifact');
    const answer = audit.answer_suggestion
      ? String(audit.answer_suggestion)
      : stringValue(audit.answer_unknown_reason, '未给出答案建议');
    return {
      key: `${questionNo ?? 'unknown'}-${index}`,
      label: questionNo ? `第 ${questionNo} 题` : `未识别题号 · 页 ${sourcePagesText(question.source_page_refs)}`,
      status,
      statusText: auditStatusText(status),
      needManualFix: Boolean(question.need_manual_fix || riskFlags.includes('need_manual_fix')),
      stem: stringValue(question.stem, '题干未能可靠定位'),
      visualSummary,
      preview: previewPath,
      answer,
      riskFlags,
    };
  });
});

const aiDebugHasFailure = computed(() =>
  aiPreviewRows.value.some((row) => row.status === 'failed' || row.needManualFix),
);

const aiDebugHeadline = computed(() => {
  if (!aiDebug.value) return 'AI预审核暂无数据';
  const rows = aiPreviewRows.value.length;
  const failures = aiPreviewRows.value.filter((row) => row.status === 'failed' || row.needManualFix).length;
  return `候选 ${rows} 条，需人工修复 ${failures} 条`;
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

async function openAiPreaudit(task: ParseTask) {
  if (!task.id) return;
  aiDrawerVisible.value = true;
  aiDebugLoading.value = true;
  aiDebugError.value = '';
  aiDebug.value = null;
  try {
    aiDebug.value = await getAiPreauditDebug(task.id);
  } catch (error) {
    aiDebugError.value = error instanceof Error ? error.message : 'AI预审核调试产物读取失败';
  } finally {
    aiDebugLoading.value = false;
  }
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

function stringValue(value: unknown, fallback: string) {
  if (typeof value === 'string') return mathTextToString(value, fallback);
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function normalizeStringList(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => stringValue(item, ''))
    .filter(Boolean);
}

function sourcePagesText(value: unknown) {
  if (!Array.isArray(value) || !value.length) return '未知';
  return value.map((item) => stringValue(item, '')).filter(Boolean).join(', ') || '未知';
}

function auditStatusText(status: string) {
  return { failed: 'failed', warning: 'warning', passed: 'passed', success: 'success' }[status] || status;
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

function openPaperReview(task: ParseTask) {
  if (!task.id) return;
  void router.push(`/pdf/tasks/${task.id}/paper-review`);
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

.ai-debug,
.ai-debug-card {
  display: grid;
  gap: 12px;
}

.ai-debug-loading,
.ai-debug-error {
  color: #6b7280;
}

.ai-debug-error {
  color: #b91c1c;
}

.ai-debug-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.ai-debug-grid div,
.ai-debug-card {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.ai-debug-grid span,
.ai-debug-card p span {
  display: block;
  margin-bottom: 4px;
  color: #6b7280;
  font-size: 12px;
}

.ai-debug-grid strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 13px;
}

.ai-debug-card-head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.ai-debug-card p {
  margin: 0;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.risk-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.task-error {
  color: #b91c1c;
}

.muted {
  color: #94a3b8;
}
</style>
