<template>
  <div class="page">
    <PageHeader />
    <el-tabs v-model="activeTab" class="system-tabs">
      <el-tab-pane label="基础配置" name="basic">
        <div class="panel list-panel">
          <h3>系统配置</h3>
          <el-table :data="configs" row-key="key">
            <el-table-column prop="key" label="Key" width="220" />
            <el-table-column prop="description" label="说明" min-width="180" />
            <el-table-column prop="value_type" label="类型" width="100" />
            <el-table-column label="值" min-width="280">
              <template #default="{ row }">
                <el-input
                  v-model="row.value"
                  :show-password="isSecret(row.key)"
                  :type="isSecret(row.key) ? 'password' : 'text'"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button link type="primary" @click="handleSave(row)">保存</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="PDF 解析服务" name="pdf">
        <div class="panel list-panel">
          <div class="status-cards">
            <div class="status-card" :class="{ online: serviceStatus.reachable, offline: !serviceStatus.reachable }">
              <span>PDF 服务</span>
              <strong>{{ serviceStatus.reachable ? '运行中' : '不可达' }}</strong>
              <small>响应 {{ serviceStatus.response_ms || 0 }}ms</small>
            </div>
            <div class="status-card">
              <span>解析队列</span>
              <strong>{{ serviceStatus.queue?.processing || 0 }} 处理中</strong>
              <small>{{ serviceStatus.queue?.pending || 0 }} 等待</small>
            </div>
            <div class="status-card">
              <span>内存占用</span>
              <strong>{{ serviceStatus.memory_mb || 0 }} MB</strong>
              <small>运行 {{ serviceStatus.uptime_seconds || 0 }} 秒</small>
            </div>
            <div class="status-card">
              <span>今日解析</span>
              <strong>{{ stats.today?.total_parsed || 0 }} 份</strong>
              <small>{{ stats.today?.total_questions || 0 }} 道题</small>
            </div>
          </div>

          <div class="provider-status">
            <el-tag
              v-for="(provider, name) in serviceStatus.ai_providers"
              :key="name"
              :type="provider.last_error ? 'danger' : 'success'"
            >
              {{ providerLabel(String(name)) }} {{ provider.last_error ? '异常' : '正常' }}
            </el-tag>
            <el-button :loading="refreshing" @click="refreshPdfPanel">刷新状态</el-button>
          </div>
        </div>

        <div class="panel list-panel">
          <div class="terminal-header">
            <h3>解析队列实时终端</h3>
            <div class="terminal-actions">
              <el-tag :type="queueLiveConnected ? 'success' : 'danger'">
                {{ queueLiveConnected ? '实时连接中' : '连接断开' }}
              </el-tag>
              <span class="refresh-time">最后刷新：{{ queueLastRefreshAt || '-' }}</span>
              <el-button size="small" :loading="refreshing" @click="refreshPdfPanel">手动刷新</el-button>
              <el-button size="small" @click="clearQueueTerminal">清屏</el-button>
            </div>
          </div>
          <pre class="queue-terminal"><code>{{ queueTerminalText }}</code></pre>
        </div>

        <div class="panel list-panel">
          <h3>AI 供应商配置</h3>
          <el-form label-width="150px" class="config-form">
            <el-form-item label="视觉 AI 供应商">
              <el-select v-model="pdfConfigForm.ai_provider_vision" class="form-input">
                <el-option label="通义千问 VL（推荐）" value="qwen_vl" />
                <el-option label="豆包视觉" value="doubao" />
                <el-option label="智谱 GLM-4V" value="zhipu" />
              </el-select>
            </el-form-item>
            <el-form-item label="文字 AI 供应商">
              <el-select v-model="pdfConfigForm.ai_provider_text" class="form-input">
                <el-option label="DeepSeek（推荐，最便宜）" value="deepseek" />
                <el-option label="通义千问" value="qwen" />
                <el-option label="豆包" value="doubao" />
              </el-select>
            </el-form-item>
            <el-form-item label="通义千问 API Key">
              <el-input
                v-model="pdfConfigForm.qwen_api_key"
                class="form-input"
                type="password"
                show-password
                :placeholder="serviceConfig.qwen_api_key_set ? '已配置（留空不修改）' : '未配置'"
              />
            </el-form-item>
            <el-form-item label="DeepSeek API Key">
              <el-input
                v-model="pdfConfigForm.deepseek_api_key"
                class="form-input"
                type="password"
                show-password
                :placeholder="serviceConfig.deepseek_api_key_set ? '已配置（留空不修改）' : '未配置'"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPdfConfig" @click="savePdfConfig">保存并生效</el-button>
              <el-button @click="runTestParse">测试连接</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="panel list-panel">
          <h3>提示词管理</h3>
          <el-collapse>
            <el-collapse-item
              v-for="prompt in promptConfigs"
              :key="prompt.key"
              :title="prompt.title"
              :name="prompt.key"
            >
              <el-input v-model="prompt.value" type="textarea" :rows="8" />
              <div class="prompt-actions">
                <el-button @click="prompt.value = prompt.defaultValue">恢复默认</el-button>
                <el-button type="primary" @click="savePrompt(prompt)">保存并清缓存</el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <div class="panel list-panel">
          <h3>解析效果测试</h3>
          <el-form inline class="test-form">
            <el-form-item label="选择题库">
              <el-select v-model="testBankId" class="bank-select" placeholder="选择已有题库">
                <el-option v-for="bank in banks" :key="bank.id" :label="bank.name" :value="bank.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="PDF URL">
              <el-input v-model="testPdfUrl" class="url-input" placeholder="输入已上传的 PDF URL" />
            </el-form-item>
            <el-form-item label="测试页码">
              <el-input v-model="testPages" class="pages-input" placeholder="如 0,1,2" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="testParsing" @click="runTestParse">测试解析</el-button>
            </el-form-item>
          </el-form>

          <div v-if="testResult" class="test-result">
            <el-alert
              :title="`解析完成：识别 ${testResult.stats?.total || testResult.stats?.total_questions || 0} 道题，过滤 ${testResult.stats?.filtered_out || 0} 条垃圾`"
              :type="(testResult.questions?.length || 0) > 0 ? 'success' : 'warning'"
              show-icon
            />
            <el-descriptions v-if="testResult.detection" title="检测结果" :column="3" size="small" border>
              <el-descriptions-item label="PDF类型">
                {{ typeLabel[testResult.detection.type] || testResult.detection.type }}
                （置信度 {{ Math.round(Number(testResult.detection.confidence || 0) * 100) }}%）
              </el-descriptions-item>
              <el-descriptions-item label="图片页比例">
                {{ Math.round(Number(testResult.detection.stats?.image_ratio || 0) * 100) }}%
              </el-descriptions-item>
              <el-descriptions-item label="目录行比例">
                {{ Math.round(Number(testResult.detection.stats?.toc_ratio || 0) * 100) }}%
              </el-descriptions-item>
            </el-descriptions>

            <div class="questions-preview">
              <div v-for="(q, index) in testResult.questions.slice(0, 5)" :key="index" class="question-card">
                <el-tag size="small" :type="q.needs_review ? 'danger' : 'success'">
                  {{ q.needs_review ? '待审核' : '正常' }}
                </el-tag>
                <span class="q-index">第{{ q.index }}题</span>
                <p class="q-content"><MathText :text="q.content" fallback="题干未能可靠定位" /></p>
                <div v-if="q.options" class="q-options">
                  <span v-for="(value, key) in q.options" :key="key">{{ key }}. <MathText :text="value" fallback="选项缺失" /> &nbsp;</span>
                </div>
                <div v-if="q.answer" class="q-answer">答案：<MathText :text="q.answer" /></div>
                <div v-if="q.images?.length" class="image-row">
                  <el-image
                    v-for="(img, imgIndex) in q.images"
                    :key="imgIndex"
                    :src="imageSrc(img)"
                    class="preview-image"
                    preview-teleported
                    :preview-src-list="q.images.map(imageSrc)"
                  />
                </div>
              </div>
              <el-text v-if="testResult.questions.length > 5" type="info">
                仅展示前5题，共 {{ testResult.questions.length }} 题
              </el-text>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="系统信息" name="info">
        <div class="panel list-panel">
          <h3>运行状态</h3>
          <el-descriptions :column="4" border>
            <el-descriptions-item v-for="(value, key) in info" :key="key" :label="key">
              {{ value }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { getBanks, type Bank } from '@/api/bank';
import { pdfServiceApi, type PdfServiceConfig, type PdfServiceStats, type PdfServiceStatus, type TestParseResult } from '@/api/pdf-service';
import { getSystemConfigs, getSystemInfo, updateSystemConfig, type SystemConfig } from '@/api/system';
import MathText from '@/components/MathText.vue';
import PageHeader from '@/components/PageHeader.vue';

interface PromptConfig {
  key: string;
  title: string;
  value: string;
  defaultValue: string;
}

const activeTab = ref('basic');
const configs = ref<SystemConfig[]>([]);
const info = ref<Record<string, unknown>>({});
const banks = ref<Bank[]>([]);
const serviceStatus = ref<Partial<PdfServiceStatus>>({});
const stats = ref<PdfServiceStats>({});
const serviceConfig = ref<Partial<PdfServiceConfig>>({});
const refreshing = ref(false);
const savingPdfConfig = ref(false);
const testParsing = ref(false);
const testBankId = ref('');
const testPdfUrl = ref('');
const testPages = ref('0,1,2');
const testResult = ref<TestParseResult | null>(null);
const queueLiveConnected = ref(false);
const queueLastRefreshAt = ref('');
const queueTerminalLines = ref<string[]>([]);
let refreshTimer: number | undefined;

const pdfConfigForm = reactive({
  ai_provider_vision: 'qwen_vl',
  ai_provider_text: 'qwen',
  qwen_api_key: '',
  deepseek_api_key: '',
});

const promptConfigs = reactive<PromptConfig[]>([
  {
    key: 'prompt.page_parse',
    title: '整页截图识别提示词（视觉AI使用）',
    value: '',
    defaultValue: '你是行测题目提取助手。请从 PDF 页面截图中提取题目并返回严格 JSON。',
  },
  {
    key: 'prompt.text_structure',
    title: '文字结构化提示词（文字AI使用）',
    value: '',
    defaultValue: '你是行测题目解析助手。请将原始文本解析为结构化 JSON 数组。',
  },
  {
    key: 'prompt.image_describe',
    title: '图表描述提示词',
    value: '',
    defaultValue: '请描述图表类型、关键数据和一句话概括，只返回 JSON。',
  },
]);

const typeLabel: Record<string, string> = {
  pure_text: '纯文字题库',
  visual_heavy: '图文混排',
  textbook: '教辅讲义',
  exam_paper: '模拟卷',
  unknown: '未识别',
};

const queueTerminalText = computed(() => [
  ...queueTerminalLines.value,
  '',
  '$ queue snapshot',
  `service_status: ${serviceStatus.value.status || '-'}`,
  `reachable: ${serviceStatus.value.reachable ?? true}`,
  `response_ms: ${serviceStatus.value.response_ms ?? '-'}`,
  `queue: pending=${serviceStatus.value.queue?.pending ?? '-'} processing=${serviceStatus.value.queue?.processing ?? '-'} completed_today=${serviceStatus.value.queue?.completed_today ?? '-'}`,
  `memory_mb: ${serviceStatus.value.memory_mb ?? '-'}`,
  `uptime_seconds: ${serviceStatus.value.uptime_seconds ?? '-'}`,
  `today: parsed=${stats.value.today?.total_parsed ?? 0} success=${stats.value.today?.success_count ?? 0} fail=${stats.value.today?.fail_count ?? 0} questions=${stats.value.today?.total_questions ?? 0}`,
  `session: parsed=${stats.value.session?.total_parsed ?? 0} questions=${stats.value.session?.total_questions ?? 0}`,
  `ai_calls: ${JSON.stringify(stats.value.session?.ai_calls || {})}`,
  `qwen_last_call_at: ${serviceStatus.value.ai_providers?.qwen_vl?.last_call_at || '-'}`,
  `qwen_last_error: ${serviceStatus.value.ai_providers?.qwen_vl?.last_error || '-'}`,
  `deepseek_last_call_at: ${serviceStatus.value.ai_providers?.deepseek?.last_call_at || '-'}`,
  `deepseek_last_error: ${serviceStatus.value.ai_providers?.deepseek?.last_error || '-'}`,
].join('\\n'));

async function fetchAll() {
  const [configList, systemInfo, bankResult] = await Promise.all([
    getSystemConfigs(),
    getSystemInfo(),
    getBanks({ page: 1, pageSize: 100 }),
  ]);
  configs.value = configList;
  info.value = systemInfo;
  banks.value = bankResult.list;
  testBankId.value ||= banks.value[0]?.id || '';
  hydratePromptConfigs();
  await refreshPdfPanel();
}

function hydratePromptConfigs() {
  for (const prompt of promptConfigs) {
    const existing = configs.value.find((config) => config.key === prompt.key);
    prompt.value = existing?.value || prompt.defaultValue;
  }
}

async function refreshPdfPanel() {
  refreshing.value = true;
  try {
    const [statusResult, statsResult, configResult] = await Promise.all([
      pdfServiceApi.getStatus(),
      pdfServiceApi.getStats(),
      pdfServiceApi.getConfig(),
    ]);
    serviceStatus.value = statusResult;
    stats.value = statsResult;
    serviceConfig.value = configResult;
    pdfConfigForm.ai_provider_vision = configResult.ai_provider_vision || 'qwen_vl';
    pdfConfigForm.ai_provider_text = configResult.ai_provider_text || 'qwen';
    queueLiveConnected.value = true;
    queueLastRefreshAt.value = new Date().toLocaleTimeString();
    appendQueueTerminal(statusResult, statsResult);
  } catch (error) {
    queueLiveConnected.value = false;
    queueLastRefreshAt.value = new Date().toLocaleTimeString();
    queueTerminalLines.value.push(`[${queueLastRefreshAt.value}] error ${error instanceof Error ? error.message : 'refresh failed'}`);
  } finally {
    refreshing.value = false;
  }
}

function appendQueueTerminal(statusResult: PdfServiceStatus, statsResult: PdfServiceStats) {
  const queue = statusResult.queue;
  const aiCalls = statsResult.session?.ai_calls || {};
  queueTerminalLines.value.push(
    `[${new Date().toLocaleTimeString()}] queue pending=${queue?.pending ?? '-'} processing=${queue?.processing ?? '-'} done_today=${queue?.completed_today ?? '-'} memory=${statusResult.memory_mb ?? '-'}MB ai=${JSON.stringify(aiCalls)}`,
  );
  if (statusResult.ai_providers?.qwen_vl?.last_error) {
    queueTerminalLines.value.push(`[${new Date().toLocaleTimeString()}] qwen_error ${statusResult.ai_providers.qwen_vl.last_error}`);
  }
  if (queueTerminalLines.value.length > 160) queueTerminalLines.value = queueTerminalLines.value.slice(-160);
}

function clearQueueTerminal() {
  queueTerminalLines.value = [];
}

async function handleSave(row: SystemConfig) {
  await updateSystemConfig(row.key, {
    value: row.value,
    description: row.description,
  });
  ElMessage.success('已保存');
}

async function savePdfConfig() {
  savingPdfConfig.value = true;
  try {
    await pdfServiceApi.updateConfig({
      ai_provider_vision: pdfConfigForm.ai_provider_vision,
      ai_provider_text: pdfConfigForm.ai_provider_text,
      qwen_api_key: pdfConfigForm.qwen_api_key || undefined,
      deepseek_api_key: pdfConfigForm.deepseek_api_key || undefined,
    });
    await Promise.all([
      updateSystemConfig('DASHSCOPE_API_KEY', {
        value: pdfConfigForm.qwen_api_key || findConfigValue('DASHSCOPE_API_KEY'),
        description: '阿里云百炼 API Key（用于通义千问 VL/文本模型）',
      }),
      updateSystemConfig('AI_VISUAL_MODEL', {
        value: 'qwen-vl-max',
        description: 'PDF 图文解析视觉模型',
      }),
      updateSystemConfig('AI_TEXT_MODEL', {
        value: pdfConfigForm.ai_provider_text === 'qwen' ? 'qwen-plus' : findConfigValue('AI_TEXT_MODEL') || 'qwen-plus',
        description: 'PDF 纯文本结构化模型',
      }),
    ]);
    pdfConfigForm.qwen_api_key = '';
    pdfConfigForm.deepseek_api_key = '';
    ElMessage.success('PDF 服务配置已更新');
    await fetchAll();
  } finally {
    savingPdfConfig.value = false;
  }
}

async function savePrompt(prompt: PromptConfig) {
  await updateSystemConfig(prompt.key, {
    value: prompt.value,
    description: prompt.title,
  });
  await pdfServiceApi.invalidateCache();
  ElMessage.success('提示词已更新，下次解析立即生效');
  await fetchAll();
}

async function runTestParse() {
  if (!testPdfUrl.value) {
    ElMessage.warning('请输入 PDF URL');
    return;
  }
  testParsing.value = true;
  try {
    testResult.value = await pdfServiceApi.testParse({
      bank_id: testBankId.value,
      file_url: testPdfUrl.value,
      pages: parsePages(testPages.value),
    });
    ElMessage.success('测试解析完成');
    await refreshPdfPanel();
  } finally {
    testParsing.value = false;
  }
}

function parsePages(value: string) {
  const pages = value
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item >= 0);
  return pages.length ? pages : undefined;
}

function findConfigValue(key: string) {
  return configs.value.find((config) => config.key === key)?.value || '';
}

function isSecret(key: string) {
  return key.toUpperCase().includes('API_KEY') || key.toUpperCase().includes('SECRET');
}

function providerLabel(name: string) {
  if (name === 'qwen_vl') return '通义千问VL';
  if (name === 'deepseek') return 'DeepSeek';
  return name;
}

function imageSrc(image: any) {
  const base64 = typeof image === 'string' ? image : image?.base64;
  return base64?.startsWith('data:') ? base64 : `data:image/png;base64,${base64 || ''}`;
}

onMounted(async () => {
  await fetchAll();
  refreshTimer = window.setInterval(refreshPdfPanel, 30_000);
});

onBeforeUnmount(() => window.clearInterval(refreshTimer));
</script>

<style scoped>
.system-tabs {
  padding: 16px;
}

.list-panel {
  margin-bottom: 16px;
  padding: 16px;
}

h3 {
  margin: 0 0 12px;
}

.status-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.status-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.status-card strong {
  font-size: 22px;
}

.status-card small,
.status-card span {
  color: #6b7280;
}

.status-card.online {
  border-color: #67c23a;
}

.status-card.offline {
  border-color: #f56c6c;
}

.provider-status,
.prompt-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.terminal-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.refresh-time {
  color: #6b7280;
  font-size: 12px;
}

.queue-terminal {
  min-height: 300px;
  max-height: 460px;
  margin: 0;
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

.form-input {
  width: 420px;
}

.test-form {
  align-items: flex-start;
}

.bank-select {
  width: 220px;
}

.url-input {
  width: 380px;
}

.pages-input {
  width: 140px;
}

.test-result {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.questions-preview {
  display: grid;
  gap: 12px;
}

.question-card {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.q-index {
  margin-left: 8px;
  font-weight: 700;
}

.q-content {
  margin: 10px 0;
}

.q-answer {
  margin-top: 8px;
  color: #15803d;
  font-weight: 700;
}

.image-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.preview-image {
  max-width: 200px;
  max-height: 160px;
}
</style>
