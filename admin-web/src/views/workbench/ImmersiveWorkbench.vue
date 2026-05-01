<template>
  <div class="workbench-page">
    <template v-if="!selectedBankId">
      <header class="workbench-header">
        <div class="title-group">
          <el-button class="back-button" circle :icon="ArrowLeft" @click="router.back()" />
          <div>
            <h1>选择题库</h1>
            <div class="header-meta">
              <el-tag effect="plain" type="info">题干审核</el-tag>
              <span>先选择要整理的题库，再进入题干审核工作台</span>
            </div>
          </div>
        </div>
        <div class="header-actions">
          <el-input
            v-model="bankKeyword"
            class="bank-search"
            clearable
            placeholder="搜索题库名称"
            :prefix-icon="Search"
            @keyup.enter="fetchBanks"
            @clear="fetchBanks"
          />
          <el-button :icon="Refresh" @click="fetchBanks">刷新</el-button>
          <el-button type="primary" :icon="Plus" @click="router.push('/banks/create')">新建题库</el-button>
        </div>
      </header>

      <main class="bank-picker-main">
        <div v-if="bankLoading" class="bank-grid">
          <el-skeleton v-for="item in 6" :key="item" class="bank-skeleton" animated>
            <template #template>
              <el-skeleton-item variant="h3" style="width: 54%" />
              <el-skeleton-item variant="text" style="width: 82%" />
              <el-skeleton-item variant="text" style="width: 46%" />
            </template>
          </el-skeleton>
        </div>

        <el-empty v-else-if="!banks.length" description="暂无题库">
          <el-button type="primary" @click="router.push('/banks/create')">新建题库</el-button>
        </el-empty>

        <div v-else class="bank-grid">
          <article v-for="bank in banks" :key="bank.id" class="bank-card">
            <div class="bank-card-head">
              <div>
                <h2>{{ bank.name }}</h2>
                <p>{{ bank.subject || '未设置科目' }} · {{ bank.year || '未设置年份' }}</p>
              </div>
              <el-tag :type="bank.status === 'published' ? 'success' : 'info'" effect="plain">
                {{ bank.status === 'published' ? '已发布' : '草稿' }}
              </el-tag>
            </div>
            <div class="bank-metrics">
              <span>
                <strong>{{ bank.total_count || 0 }}</strong>
                题目
              </span>
              <span>
                <strong>{{ bank.source || '-' }}</strong>
                来源
              </span>
            </div>
            <div class="bank-card-actions">
              <el-button @click="router.push(`/banks/${bank.id}/questions`)">题目列表</el-button>
              <el-button @click="router.push(`/banks/${bank.id}/review`)">审核</el-button>
              <el-button type="primary" @click="enterWorkbench(bank.id)">制卷工作台</el-button>
            </div>
          </article>
        </div>
      </main>
    </template>

    <template v-else>
    <header class="workbench-header">
      <div class="title-group">
        <el-button class="back-button" circle :icon="ArrowLeft" @click="router.push('/workbench')" />
        <div>
          <h1>{{ activeBank?.name || questionData.title }}</h1>
          <div class="header-meta">
            <el-tag effect="plain" type="info">制卷审核</el-tag>
            <el-tag effect="plain">{{ activeBank?.subject || '当前题库' }}</el-tag>
            <span class="save-state" :class="saveState">{{ saveStateText }}</span>
          </div>
        </div>
      </div>

      <div class="header-actions">
        <el-button :disabled="currentQuestionIndex <= 0 || workbenchLoading" @click="selectQuestionByOffset(-1)">上一题</el-button>
        <el-button :disabled="currentQuestionIndex >= questions.length - 1 || workbenchLoading" @click="selectQuestionByOffset(1)">下一题</el-button>
        <el-button :disabled="!lastSnapshot" :icon="RefreshLeft" @click="handleUndo">撤销最近修复</el-button>
        <el-button type="primary" :icon="DocumentChecked" :loading="saving" :disabled="!selectedQuestion" @click="manualSave">保存草稿</el-button>
        <el-button :loading="saving" :disabled="!selectedQuestion" @click="markNeedsReview">标记需复核</el-button>
        <el-button type="success" :icon="DocumentChecked" :loading="saving" :disabled="!selectedQuestion || !questionData.stem.trim()" @click="markStemReviewed">题干审核通过</el-button>
      </div>
    </header>

    <main v-loading="workbenchLoading" class="workbench-main">
      <section class="pane pdf-pane">
        <div class="pane-head">
          <div>
            <strong>原卷定位</strong>
            <span>{{ selectedQuestion?.pdf_source?.file_name || '当前题目原始 PDF' }}</span>
          </div>
          <el-tag size="small" type="primary" effect="plain">第 {{ currentPdfPage }} 页</el-tag>
        </div>

        <div class="real-pdf-shell">
          <PdfLocator
            v-if="pdfLocatorSrc"
            v-model:page="currentPdfPage"
            :src="pdfLocatorSrc"
            :open-src="selectedQuestion?.pdf_source?.file_url"
            :headers="pdfRequestHeaders"
            :highlights="pdfHighlights"
            selection-enabled
            @region-selected="handleRegionSelected"
          />
          <div v-else class="pdf-missing">
            <strong>该题没有原始 PDF 来源</strong>
            <span>请先通过“上传 PDF”解析题库，再进入题干审核工作台定位原卷。</span>
          </div>
        </div>
      </section>

      <section class="pane editor-pane">
        <div class="pane-head">
          <div>
            <strong>题目结构与 AI 审核</strong>
            <span>在制卷流程内校对题干、选项、图片、答案和 AI 建议</span>
          </div>
        </div>

        <el-form class="editor-form" label-position="top">
          <div class="stage-note">
            制卷时可直接处理 AI 候选答案和解析；采纳或忽略都会写入审计日志，保存前会提示未处理的 AI 风险题。
          </div>

          <section class="paper-question-queue">
            <div class="queue-head">
              <div>
                <strong>制卷题目队列</strong>
                <span>{{ filteredWorkbenchQuestions.length }} / {{ questions.length }} 题</span>
              </div>
              <div class="queue-filters">
                <button
                  v-for="filter in aiQueueFilters"
                  :key="filter.value"
                  type="button"
                  :class="{ active: aiQueueFilter === filter.value }"
                  @click="aiQueueFilter = filter.value"
                >
                  {{ filter.label }}
                </button>
              </div>
            </div>
            <div class="queue-list">
              <button
                v-for="question in filteredWorkbenchQuestions"
                :key="question.id"
                type="button"
                class="queue-question"
                :class="{ active: selectedQuestion?.id === question.id, risk: hasUnresolvedAiRisk(question) }"
                @click="selectQueueQuestion(question)"
              >
                <div class="queue-question-main">
                  <strong>{{ question.index_num }}.</strong>
                  <span><MathText :text="questionBrief(question)" fallback="题干未能可靠定位" /></span>
                </div>
                <div class="queue-ai-tags">
                  <span class="queue-tag" :class="aiAuditTagClass(question)">
                    AI 预审核：{{ aiAuditQueueLabel(question) }}
                  </span>
                  <span v-if="question.answer" class="queue-tag">当前 <MathText :text="question.answer" /></span>
                  <span v-if="question.ai_candidate_answer" class="queue-tag candidate">AI <MathText :text="question.ai_candidate_answer" /></span>
                  <span v-if="aiConfidenceText(question)" class="queue-tag" :class="{ warning: isLowAiConfidence(question) }">{{ aiConfidenceText(question) }}</span>
                  <span v-if="question.ai_answer_conflict" class="queue-tag danger">答案冲突</span>
                  <span v-if="question.ai_solver_rechecked" class="queue-tag warning">Pro 复核</span>
                  <span v-if="isAiIgnored(question)" class="queue-tag muted">已忽略</span>
                  <span v-if="latestAiAction(question)" class="queue-tag muted">{{ aiActionLabel(latestAiAction(question)?.action || '') }}</span>
                  <span v-if="question.ai_solver_final_model || question.ai_solver_model" class="queue-tag model">{{ question.ai_solver_final_model || question.ai_solver_model }}</span>
                  <span v-for="flag in aiRiskFlags(question)" :key="flag" class="queue-tag warning">{{ flag }}</span>
                </div>
              </button>
            </div>
          </section>

          <div v-if="selectedQuestion?.answer || selectedQuestion?.analysis" class="current-answer-panel">
            <div>
              <span>当前答案</span>
              <strong><MathText :text="selectedQuestion?.answer" fallback="-" /></strong>
            </div>
            <p v-if="selectedQuestion?.analysis"><MathText :text="selectedQuestion.analysis" /></p>
          </div>

          <div v-if="aiPreaudit.visible" class="ai-preaudit-panel" :class="aiPreaudit.statusClass">
            <div class="ai-preaudit-head">
              <strong>AI 预审核：{{ aiPreaudit.verdict }}</strong>
              <div>
                <el-tag size="small" :type="aiPreaudit.tagType" effect="plain">
                  {{ aiPreaudit.statusText }}
                </el-tag>
                <el-tag v-if="aiPreaudit.confidenceText" size="small" type="info" effect="plain">
                  {{ aiPreaudit.confidenceText }}
                </el-tag>
              </div>
            </div>
            <div class="ai-preaudit-grid">
              <span>理解题目</span>
              <p>{{ aiPreaudit.understandText }}</p>
              <span>可作答</span>
              <p>{{ aiPreaudit.solveText }}</p>
              <span>AI 建议答案</span>
              <p><MathText :text="aiPreaudit.answerText" /></p>
              <span>AI 解析建议</span>
              <p><MathText :text="aiPreaudit.analysisText" /></p>
              <span>图表摘要</span>
              <p>{{ aiPreaudit.visualText }}</p>
              <span v-if="aiPreaudit.riskFlags.length">风险提示</span>
              <div v-if="aiPreaudit.riskFlags.length" class="ai-tag-row">
                <el-tag v-for="flag in aiPreaudit.riskFlags" :key="flag" size="small" type="warning" effect="plain">
                  {{ flag }}
                </el-tag>
              </div>
            </div>
          </div>

          <div v-if="aiAssistance.visible" class="ai-assist-panel">
            <div class="ai-assist-head">
              <strong>视觉 AI 判断</strong>
              <div>
                <el-tag size="small" effect="plain">{{ aiAssistance.provider }}</el-tag>
                <el-tag v-if="aiAssistance.model" size="small" type="info" effect="plain">
                  {{ aiAssistance.model }}
                </el-tag>
                <el-tag v-if="aiAssistance.confidenceText" size="small" type="success" effect="plain">
                  {{ aiAssistance.confidenceText }}
                </el-tag>
              </div>
            </div>
            <div class="ai-assist-grid">
              <span>Provider</span>
              <p>{{ aiAssistance.provider }}</p>
              <span>Model</span>
              <p>{{ aiAssistance.model || '-' }}</p>
              <span v-if="aiAssistance.notes">判断备注</span>
              <p v-if="aiAssistance.notes">{{ aiAssistance.notes }}</p>
            </div>
            <div v-if="aiAssistance.corrections.length" class="ai-corrections">
              <div v-for="(correction, index) in aiAssistance.corrections" :key="index" class="ai-correction-row">
                <el-tag size="small" :type="correction.status === 'applied' ? 'success' : 'warning'" effect="plain">
                  {{ correction.status || 'suggested' }}
                </el-tag>
                <span>{{ correction.action || 'vision_ai' }}</span>
                <small>{{ correction.reason || '视觉模型给出辅助判断' }}</small>
              </div>
            </div>
          </div>

          <div v-if="aiSolverAssist.visible" class="ai-solver-panel" :class="{ conflict: aiSolverAssist.conflict, caution: aiSolverAssist.lowConfidence, ignored: aiSolverAssist.ignored }">
            <div class="ai-solver-head">
              <strong>AI 候选解析</strong>
              <div>
                <el-tag v-if="aiSolverAssist.ignored" size="small" type="info" effect="plain">
                  已忽略
                </el-tag>
                <el-tag v-if="aiSolverAssist.provider" size="small" effect="plain">
                  {{ aiSolverAssist.provider }}
                </el-tag>
                <el-tag v-if="aiSolverAssist.model" size="small" type="info" effect="plain">
                  {{ aiSolverAssist.model }}
                </el-tag>
                <el-tag v-if="aiSolverAssist.rechecked" size="small" type="warning" effect="plain">
                  已 Pro 复核
                </el-tag>
                <el-tag v-if="aiSolverAssist.confidenceText" size="small" :type="aiSolverAssist.lowConfidence ? 'warning' : 'success'" effect="plain">
                  {{ aiSolverAssist.confidenceText }}
                </el-tag>
                <el-tag v-if="aiSolverAssist.conflict" size="small" type="danger" effect="plain">
                  与官方答案冲突
                </el-tag>
              </div>
            </div>
            <el-alert
              v-if="aiSolverAssist.conflict"
              title="AI 候选答案与官方答案不一致，采纳前需要人工复核。"
              type="error"
              :closable="false"
              show-icon
            />
            <el-alert
              v-else-if="aiSolverAssist.lowConfidence"
              title="AI 候选答案置信度低于 70%，建议只作为参考。"
              type="warning"
              :closable="false"
              show-icon
            />
            <div class="ai-answer-compare">
              <div class="answer-box official">
                <span>官方答案</span>
                <strong><MathText :text="aiSolverAssist.officialAnswer" fallback="-" /></strong>
              </div>
              <div class="answer-box candidate">
                <span>AI 候选答案</span>
                <strong><MathText :text="aiSolverAssist.answer" fallback="-" /></strong>
              </div>
            </div>
            <div class="ai-solver-grid">
              <span v-if="aiSolverAssist.firstModel">首轮模型</span>
              <p v-if="aiSolverAssist.firstModel">{{ aiSolverAssist.firstModel }}</p>
              <span v-if="aiSolverAssist.finalModel">最终模型</span>
              <p v-if="aiSolverAssist.finalModel">{{ aiSolverAssist.finalModel }}</p>
              <span v-if="aiSolverAssist.recheckReason">复核原因</span>
              <p v-if="aiSolverAssist.recheckReason">{{ aiSolverAssist.recheckReason }}</p>
              <span v-if="aiSolverAssist.summary">推理摘要</span>
              <p v-if="aiSolverAssist.summary">{{ aiSolverAssist.summary }}</p>
              <span v-if="aiSolverAssist.knowledgePoints.length">知识点</span>
              <div v-if="aiSolverAssist.knowledgePoints.length" class="ai-tag-row">
                <el-tag v-for="item in aiSolverAssist.knowledgePoints" :key="item" size="small" effect="plain">
                  {{ item }}
                </el-tag>
              </div>
              <span v-if="aiSolverAssist.riskFlags.length">风险</span>
              <div v-if="aiSolverAssist.riskFlags.length" class="ai-tag-row">
                <el-tag v-for="item in aiSolverAssist.riskFlags" :key="item" size="small" type="warning" effect="plain">
                  {{ item }}
                </el-tag>
              </div>
            </div>
            <el-collapse v-if="aiSolverAssist.analysis" class="ai-analysis-collapse">
              <el-collapse-item title="DeepSeek 候选解析" name="analysis">
                <div class="ai-analysis-text"><MathText :text="aiSolverAssist.analysis" /></div>
              </el-collapse-item>
            </el-collapse>
            <div v-if="aiSolverAssist.latestAction" class="ai-audit-line">
              <span>最近一次 AI 操作</span>
              <strong>{{ aiActionLabel(aiSolverAssist.latestAction.action) }}</strong>
              <small>{{ formatActionTime(aiSolverAssist.latestAction.created_at) }}</small>
              <small v-if="aiSolverAssist.latestAction.operator_id">操作人 {{ aiSolverAssist.latestAction.operator_id }}</small>
            </div>
            <div v-if="aiSolverAssist.actionLogs.length" class="ai-action-history">
              <strong>AI 操作记录</strong>
              <div v-for="log in aiSolverAssist.actionLogs" :key="log.id" class="ai-history-row">
                <span>{{ aiActionLabel(log.action) }}</span>
                <small>{{ formatActionTime(log.created_at) }}</small>
                <small v-if="log.operator_id">操作人 {{ log.operator_id }}</small>
              </div>
            </div>
            <div class="ai-accept-actions">
              <el-button size="small" :loading="aiAccepting === 'answer'" :disabled="!aiSolverAssist.answer" @click="handleAcceptAiSuggestion('answer')">
                接受 AI 答案
              </el-button>
              <el-button size="small" :loading="aiAccepting === 'analysis'" :disabled="!aiSolverAssist.analysis" @click="handleAcceptAiSuggestion('analysis')">
                接受 AI 解析
              </el-button>
              <el-button size="small" type="primary" :loading="aiAccepting === 'both'" :disabled="!aiSolverAssist.answer && !aiSolverAssist.analysis" @click="handleAcceptAiSuggestion('both')">
                同时接受答案和解析
              </el-button>
              <el-button size="small" :loading="aiAccepting === 'ignore'" :disabled="aiSolverAssist.ignored" @click="handleIgnoreAiSuggestion">
                忽略 AI 建议
              </el-button>
            </div>
          </div>

          <el-form-item label="题干">
            <el-input v-model="questionData.stem" :autosize="{ minRows: 5, maxRows: 8 }" type="textarea" />
          </el-form-item>

          <div class="image-editor">
            <div class="field-head">
              <div>
                <strong>题目图片</strong>
                <span>用于资料图、图表题、题干截图等图片型题目</span>
              </div>
              <div class="image-actions">
                <el-select v-model="selectedImageSlot" size="small" class="slot-select">
                  <el-option label="插入到题干下方" value="stem" />
                  <el-option label="插入到选项上方" value="options" />
                </el-select>
                <input
                  ref="imageInputRef"
                  class="hidden-file-input"
                  type="file"
                  accept="image/*"
                  @change="handleImageFileChange"
                />
              </div>
            </div>

            <div
              v-if="questionData.images.length === 0"
              class="image-empty"
              role="button"
              tabindex="0"
              @click="openImagePicker"
              @keydown.enter.prevent="openImagePicker"
              @keydown.space.prevent="openImagePicker"
            >
              <el-icon><Picture /></el-icon>
              <div>
                <strong>点击此处上传图片</strong>
                <span>支持资料图、图表题和题干截图，将按上方位置插入到题目中。</span>
              </div>
            </div>
            <div v-else class="image-list">
              <div v-for="image in questionData.images" :key="image.id" class="image-item">
                <img :src="image.src" :alt="image.name" />
                <div class="image-meta">
                  <strong>{{ image.name }}</strong>
                  <el-tag v-if="imageAiStatus(image.id)" size="small" type="success" effect="plain">
                    AI 已调整
                  </el-tag>
                  <el-select v-model="image.slot" size="small">
                    <el-option label="题干下方" value="stem" />
                    <el-option label="选项上方" value="options" />
                  </el-select>
                </div>
                <el-button circle plain size="small" :icon="Delete" @click="removeImage(image.id)" />
              </div>
            </div>
          </div>

          <div class="option-editor">
            <div v-for="option in questionData.options" :key="option.key" class="option-row">
              <el-input v-model="option.text">
                <template #prepend>{{ option.key }}</template>
              </el-input>
            </div>
          </div>
        </el-form>
      </section>

      <section class="pane preview-pane">
        <div class="pane-head">
          <div>
            <strong>题本预览</strong>
            <span>无答案预览，检查移动端题干和选项排版</span>
          </div>
        </div>

        <div class="phone-wrap">
          <div class="phone-frame">
            <div class="phone-speaker"></div>
            <div class="phone-screen">
            <div class="phone-status">
                <span>{{ selectedQuestion?.type === 'judge' ? '判断题' : '单选题' }} · 未匹配答案</span>
                <strong>{{ selectedQuestion?.index_num || '-' }} / {{ questions.length || '-' }}</strong>
              </div>
              <div v-if="aiPreaudit.visible" class="phone-ai-audit">
                <strong>AI 预审核：{{ aiPreaudit.verdict }}</strong>
                <span><MathText :text="aiPreaudit.answerText" /></span>
                <span>{{ aiPreaudit.visualText }}</span>
              </div>
              <h2><MathText :text="questionData.stem" fallback="题干未能可靠定位" /></h2>
              <div v-if="imagesFor('stem').length" class="phone-images">
                <img v-for="image in imagesFor('stem')" :key="image.id" :src="image.src" :alt="image.name" />
              </div>
              <div v-if="imagesFor('options').length" class="phone-images">
                <img v-for="image in imagesFor('options')" :key="image.id" :src="image.src" :alt="image.name" />
              </div>
              <div class="phone-options">
                <div
                  v-for="option in questionData.options"
                  :key="option.key"
                  class="phone-option"
                >
                  <span>{{ option.key }}</span>
                  <p><MathText :text="option.text" fallback="选项缺失" /></p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { ArrowLeft, Delete, DocumentChecked, Picture, Plus, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue';
import { getBanks, type Bank } from '@/api/bank';
import { pdfProxyUrl } from '@/api/pdf';
import { applyQuestionAiAction, getQuestion, getQuestions, updateQuestion, type Question, type QuestionAiAction } from '@/api/question';
import MathText from '@/components/MathText.vue';
import PdfLocator from '@/components/PdfLocator.vue';
import { mathTextToString } from '@/utils/mathText';
import { buildSourceHighlights, sourcePageForQuestion } from '@/utils/pdfHighlights';

type OptionKey = 'A' | 'B' | 'C' | 'D';
type ImageSlot = 'stem' | 'options';
type AiQueueFilter = 'all' | 'conflict' | 'low_confidence' | 'rechecked' | 'ignored' | 'unreviewed' | 'high_risk';

interface QuestionOption {
  key: OptionKey;
  text: string;
}

interface QuestionImage {
  id: string;
  name: string;
  src: string;
  slot: ImageSlot;
  meta?: Record<string, unknown>;
}

interface QuestionData {
  title: string;
  stem: string;
  options: QuestionOption[];
  images: QuestionImage[];
}

type RegionSelection = {
  page_num: number;
  bbox: [number, number, number, number];
};

const route = useRoute();
const router = useRouter();
const imageInputRef = ref<HTMLInputElement | null>(null);
const saveState = ref<'idle' | 'saving' | 'saved'>('saved');
const selectedImageSlot = ref<ImageSlot>('stem');
const lastSnapshot = ref<QuestionData | null>(null);
const bankLoading = ref(false);
const workbenchLoading = ref(false);
const saving = ref(false);
const aiAccepting = ref<'' | 'answer' | 'analysis' | 'both' | 'ignore'>('');
const banks = ref<Bank[]>([]);
const questions = ref<Question[]>([]);
const selectedQuestion = ref<Question | null>(null);
const bankKeyword = ref('');
const aiQueueFilter = ref<AiQueueFilter>('all');
const currentPdfPage = ref(1);

const selectedBankId = computed(() => String(route.query.bankId || ''));
const activeBank = computed(() => banks.value.find((bank) => bank.id === selectedBankId.value));
const currentQuestionIndex = computed(() => {
  if (!selectedQuestion.value) return -1;
  return questions.value.findIndex((question) => question.id === selectedQuestion.value?.id);
});

const questionData = reactive<QuestionData>({
  title: '',
  stem: '',
  options: [
    { key: 'A', text: '' },
    { key: 'B', text: '' },
    { key: 'C', text: '' },
    { key: 'D', text: '' },
  ],
  images: [],
});

const aiQueueFilters: Array<{ label: string; value: AiQueueFilter }> = [
  { label: '全部', value: 'all' },
  { label: '答案冲突', value: 'conflict' },
  { label: '低置信度', value: 'low_confidence' },
  { label: 'Pro 复核', value: 'rechecked' },
  { label: '已忽略', value: 'ignored' },
  { label: '未处理', value: 'unreviewed' },
  { label: '高风险/缺上下文', value: 'high_risk' },
];

let saveTimer: number | undefined;
let hydratingQuestion = false;

const saveStateText = computed(() => {
  if (saveState.value === 'saving') return '保存中...';
  if (saveState.value === 'saved') return '已保存';
  return '有未保存修改';
});

const sourcePage = computed(() => sourcePageForQuestion(selectedQuestion.value));
const pdfLocatorSrc = computed(() => {
  const taskId = selectedQuestion.value?.pdf_source?.task_id;
  return taskId ? pdfProxyUrl(taskId) : selectedQuestion.value?.pdf_source?.file_url || '';
});
const pdfRequestHeaders = computed(() => {
  const token = localStorage.getItem('admin_token');
  return token ? { Authorization: `Bearer ${token}` } : undefined;
});
const pdfHighlights = computed(() => buildSourceHighlights(selectedQuestion.value));
const aiAssistance = computed(() => {
  const question = selectedQuestion.value;
  const corrections = question?.ai_corrections || [];
  const confidence = Number(question?.ai_confidence);
  const correctionProvider = corrections.find((item) => item.provider)?.provider;
  return {
    visible: Boolean(question?.ai_provider || question?.ai_review_notes || corrections.length),
    provider: question?.ai_provider || 'vision-ai',
    model: correctionProvider || question?.ai_provider || 'qwen-vl',
    confidenceText: Number.isFinite(confidence) ? `置信度 ${Math.round(confidence * 100)}%` : '',
    notes: question?.ai_review_notes || '',
    corrections,
  };
});
const aiPreaudit = computed(() => {
  const question = selectedQuestion.value;
  const status = String(question?.ai_audit_status || '').trim();
  const confidence = Number(question?.ai_answer_confidence ?? question?.visual_confidence ?? question?.ai_confidence);
  const riskFlags = aiRiskFlags(question);
  const visualText = cleanDisplayText(
    question?.visual_summary
      || imageVisualSummary(question)
      || question?.visual_error
      || (question?.has_visual_context ? '视觉解析失败，需人工复核' : '无图表依赖'),
  );
  const answerText = question?.ai_candidate_answer
    ? `AI 建议答案：${question.ai_candidate_answer}`
    : cleanDisplayText(question?.answer_unknown_reason || 'AI 暂无法给出答案，需复核');
  const analysisText = question?.ai_candidate_analysis
    ? cleanDisplayText(question.ai_candidate_analysis)
    : cleanDisplayText(question?.analysis_unknown_reason || 'AI 暂无法生成解析，需复核');
  return {
    visible: Boolean(
      question
        && (
          status
          || question.ai_reviewed_before_human
          || question.ai_candidate_answer
          || question.ai_candidate_analysis
          || question.visual_parse_status
          || question.has_visual_context
        ),
    ),
    status,
    statusText: aiAuditStatusLabel(status),
    verdict: cleanDisplayText(question?.ai_audit_verdict || aiAuditStatusLabel(status)),
    statusClass: `status-${status || 'skipped'}`,
    tagType: aiAuditTagType(status),
    confidenceText: Number.isFinite(confidence) ? `置信度 ${Math.round(confidence * 100)}%` : '',
    understandText: question?.ai_can_understand_question ? 'AI 已理解题目' : 'AI 暂无法理解题目，需人工复核',
    solveText: question?.ai_can_solve_question ? 'AI 判断可作答' : 'AI 暂无法判断答案，需人工复核',
    answerText,
    analysisText,
    visualText,
    riskFlags,
  };
});
const aiSolverAssist = computed(() => {
  const question = selectedQuestion.value;
  const confidence = Number(question?.ai_answer_confidence);
  const knowledgePoints = question?.ai_knowledge_points || [];
  const riskFlags = question?.ai_risk_flags || [];
  const lowConfidence = Number.isFinite(confidence) && confidence < 0.7;
  const actionLogs = question?.ai_action_logs || [];
  const latestAction = actionLogs[0] || null;
  return {
    visible: Boolean(
      question?.ai_candidate_answer
      || question?.ai_candidate_analysis
      || question?.ai_reasoning_summary
      || question?.ai_solver_provider
      || question?.ai_solver_rechecked
      || question?.ai_answer_conflict,
    ),
    provider: question?.ai_solver_provider || '',
    model: question?.ai_solver_final_model || question?.ai_solver_model || '',
    firstModel: question?.ai_solver_first_model || '',
    finalModel: question?.ai_solver_final_model || question?.ai_solver_model || '',
    rechecked: Boolean(question?.ai_solver_rechecked),
    recheckReason: question?.ai_solver_recheck_reason || '',
    officialAnswer: question?.answer || '',
    answer: question?.ai_candidate_answer || '',
    analysis: question?.ai_candidate_analysis || '',
    summary: question?.ai_reasoning_summary || '',
    confidenceText: Number.isFinite(confidence) ? `置信度 ${Math.round(confidence * 100)}%` : '',
    lowConfidence,
    latestAction,
    actionLogs,
    ignored: latestAction?.action === 'ignore_ai_suggestion',
    knowledgePoints,
    riskFlags,
    conflict: Boolean(question?.ai_answer_conflict),
  };
});
const filteredWorkbenchQuestions = computed(() => questions.value.filter((question) => {
  if (aiQueueFilter.value === 'all') return true;
  if (aiQueueFilter.value === 'conflict') return Boolean(question.ai_answer_conflict);
  if (aiQueueFilter.value === 'low_confidence') return isLowAiConfidence(question);
  if (aiQueueFilter.value === 'rechecked') return Boolean(question.ai_solver_rechecked);
  if (aiQueueFilter.value === 'ignored') return isAiIgnored(question);
  if (aiQueueFilter.value === 'unreviewed') return hasAiSuggestion(question) && !latestAiAction(question);
  return isHighRiskAiQuestion(question);
}));
const unresolvedAiRiskQuestions = computed(() => questions.value.filter(hasUnresolvedAiRisk));

async function fetchBanks() {
  bankLoading.value = true;
  try {
    const result = await getBanks({
      page: 1,
      pageSize: 100,
      keyword: bankKeyword.value || undefined,
    });
    banks.value = result.list;
  } finally {
    bankLoading.value = false;
  }
}

function enterWorkbench(bankId: string) {
  void router.push({ path: '/workbench', query: { bankId } });
}

// 数据绑定：中栏表单直接修改 questionData；右栏只读取同一个响应式对象，因此编辑和预览天然同步。
watch(
  questionData,
  () => {
    if (hydratingQuestion || !selectedQuestion.value) return;
    saveState.value = 'saving';
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      saveState.value = 'idle';
    }, 1500);
  },
  { deep: true },
);

watch(
  selectedBankId,
  (bankId) => {
    if (bankId) {
      void fetchWorkbenchQuestions(bankId);
    } else {
      questions.value = [];
      selectedQuestion.value = null;
      hydrateQuestionData(null);
    }
  },
  { immediate: true },
);

async function fetchWorkbenchQuestions(bankId: string) {
  workbenchLoading.value = true;
  try {
    const result = await getQuestions({ bankId, page: 1, pageSize: 100, include_ai_action_logs: true });
    questions.value = result.list;
    const requestedQuestionId = String(route.query.questionId || '');
    const first = requestedQuestionId
      ? questions.value.find((question) => question.id === requestedQuestionId) || questions.value[0]
      : questions.value[0];
    if (!first) {
      selectedQuestion.value = null;
      hydrateQuestionData(null);
      return;
    }
    await loadQuestion(first.id);
  } finally {
    workbenchLoading.value = false;
  }
}

async function loadQuestion(questionId: string) {
  const detail = await getQuestion(questionId);
  selectedQuestion.value = detail;
  replaceQuestionInList(detail);
  hydrateQuestionData(detail);
  currentPdfPage.value = Math.max(1, Number(sourcePage.value) || 1);
}

async function selectQueueQuestion(question: Question) {
  await loadQuestion(question.id);
  void router.replace({ path: '/workbench', query: { bankId: selectedBankId.value, questionId: question.id } });
}

async function selectQuestionByOffset(offset: number) {
  const nextIndex = currentQuestionIndex.value + offset;
  const target = questions.value[nextIndex];
  if (!target) return;
  await loadQuestion(target.id);
  void router.replace({ path: '/workbench', query: { bankId: selectedBankId.value, questionId: target.id } });
}

function hydrateQuestionData(question: Question | null) {
  hydratingQuestion = true;
  try {
    questionData.title = question ? `第 ${question.index_num} 题` : '';
    questionData.stem = cleanQuestionText(question?.content);
    questionData.options = [
      { key: 'A', text: question?.option_a || '' },
      { key: 'B', text: question?.option_b || '' },
      { key: 'C', text: question?.option_c || '' },
      { key: 'D', text: question?.option_d || '' },
    ];
    questionData.images = normalizeQuestionImages(question?.images || []);
    saveState.value = question ? 'saved' : 'idle';
    lastSnapshot.value = null;
  } finally {
    hydratingQuestion = false;
  }
}

function cleanQuestionText(value: unknown) {
  return cleanDisplayText(value)
    .split(/\r?\n/)
    .filter((line) => !['【', '】', '【】'].includes(line.trim()))
    .join('\n')
    .replace(/^[\s\r\n]*[【】]+[\s\r\n]*/g, '')
    .replace(/[\s\r\n]*[【】]+[\s\r\n]*$/g, '')
    .trim();
}

function cleanDisplayText(value: unknown) {
  return mathTextToString(value, '')
    .split(/\r?\n/)
    .map((line) => line.replace(/\[?\s*(?:page\s*\d+\s*)?visual\s+parse\s+(?:unavailable|failed|error)[^\]\r\n]*\]?/gi, '').trim())
    .filter((line) => line && !/^\[?\s*unavailable\s*\]?$/i.test(line))
    .join('\n')
    .trim();
}

function normalizeQuestionImages(images: NonNullable<Question['images']>): QuestionImage[] {
  return images
    .map((image, index) => {
      if (typeof image === 'string') {
        return {
          id: `image-${index}`,
          name: `题目图片 ${index + 1}`,
          src: image,
          slot: 'stem' as ImageSlot,
        };
      }
      const role = image.image_role || image.role || '';
      const insertPosition = image.insert_position || '';
      const slot: ImageSlot =
        role === 'option_image' || insertPosition === 'above_options' || insertPosition === 'below_options'
          ? 'options'
          : 'stem';
      const src = image.url || (image.base64 ? `data:image/png;base64,${image.base64}` : '');
      return {
        id: image.ref || `image-${index}`,
        name: image.caption || image.ref || `题目图片 ${index + 1}`,
        src,
        slot,
        meta: { ...image },
      };
    })
    .filter((image) => image.src);
}

function cloneQuestionData(): QuestionData {
  return JSON.parse(JSON.stringify(questionData)) as QuestionData;
}

function restoreQuestionData(snapshot: QuestionData) {
  questionData.title = snapshot.title;
  questionData.stem = snapshot.stem;
  questionData.options = snapshot.options.map((option) => ({ ...option }));
  questionData.images = snapshot.images.map((image) => ({ ...image }));
}

function imagesFor(slot: ImageSlot) {
  return questionData.images.filter((image) => image.slot === slot);
}

function imageAiStatus(imageId: string) {
  const corrections = selectedQuestion.value?.ai_corrections || [];
  return corrections.some((correction) => {
    if (correction.status !== 'applied') return false;
    const refs = correction.updates?.visual_refs;
    return Array.isArray(refs) && refs.map(String).includes(imageId);
  });
}

function replaceQuestionInList(question: Question) {
  const index = questions.value.findIndex((item) => item.id === question.id);
  if (index >= 0) {
    questions.value[index] = { ...questions.value[index], ...question };
  }
}

function questionBrief(question: Question) {
  const content = cleanDisplayText(question.content || '暂无题干').replace(/\s+/g, ' ').trim();
  return content.length > 72 ? `${content.slice(0, 72)}...` : content;
}

function hasAiSuggestion(question: Question | null | undefined) {
  return Boolean(
    question?.ai_candidate_answer
      || question?.ai_candidate_analysis
      || question?.ai_review_notes
      || question?.ai_corrections?.length
      || question?.ai_solver_provider
      || question?.ai_audit_status
      || question?.ai_reviewed_before_human
  );
}

function aiAuditQueueLabel(question: Question | null | undefined) {
  return aiAuditStatusLabel(String(question?.ai_audit_status || ''));
}

function aiAuditStatusLabel(status: string) {
  if (status === 'passed') return '通过';
  if (status === 'warning') return '需复核';
  if (status === 'failed') return '失败';
  if (status === 'skipped') return '未完成，需复核';
  return '未完成，需复核';
}

function aiAuditTagClass(question: Question | null | undefined) {
  const status = String(question?.ai_audit_status || '');
  if (status === 'passed') return 'candidate';
  if (status === 'failed') return 'danger';
  if (status === 'warning') return 'warning';
  return 'muted';
}

function aiAuditTagType(status: string) {
  if (status === 'passed') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'warning') return 'warning';
  return 'info';
}

function latestAiAction(question: Question | null | undefined) {
  return question?.ai_action_logs?.[0] || null;
}

function isAiIgnored(question: Question | null | undefined) {
  return latestAiAction(question)?.action === 'ignore_ai_suggestion';
}

function aiRiskFlags(question: Question | null | undefined) {
  return [
    ...(Array.isArray(question?.ai_risk_flags) ? question.ai_risk_flags.map(String) : []),
    ...(Array.isArray(question?.visual_risk_flags) ? question.visual_risk_flags.map(String) : []),
  ].map(cleanDisplayText).filter(Boolean);
}

function imageVisualSummary(question: Question | null | undefined) {
  const images = Array.isArray(question?.images) ? question?.images || [] : [];
  const summaries = images
    .map((image) => (typeof image === 'string' ? '' : cleanDisplayText(image.visual_summary || image.visual_error || image.ai_desc || image.caption || '')))
    .filter(Boolean);
  return summaries[0] || '';
}

function aiConfidenceText(question: Question | null | undefined) {
  const confidence = Number(question?.ai_answer_confidence);
  return Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : '';
}

function isLowAiConfidence(question: Question | null | undefined) {
  const confidence = Number(question?.ai_answer_confidence);
  return Number.isFinite(confidence) && confidence < 0.7;
}

function isHighRiskAiQuestion(question: Question | null | undefined) {
  const flags = new Set(aiRiskFlags(question));
  return Boolean(flags.has('missing_context') || flags.has('requires_table') || flags.has('requires_chart'));
}

function hasUnresolvedAiRisk(question: Question | null | undefined) {
  if (!question || latestAiAction(question)) return false;
  return Boolean(
    question.ai_answer_conflict
      || isLowAiConfidence(question)
      || isHighRiskAiQuestion(question)
      || question.ai_candidate_answer
      || question.ai_candidate_analysis,
  );
}

function openImagePicker() {
  imageInputRef.value?.click();
}

// 图片结构化字段：用 data URL 暂存本地选择，便于当前编辑、撤销和右侧 H5 预览同步验证。
function handleImageFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件');
    input.value = '';
    return;
  }

  lastSnapshot.value = cloneQuestionData();
  const reader = new FileReader();
  reader.onload = () => {
    questionData.images.push({
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: file.name,
      src: String(reader.result),
      slot: selectedImageSlot.value,
    });
    ElMessage.success('图片已插入结构化题目');
  };
  reader.readAsDataURL(file);
  input.value = '';
}

function removeImage(id: string) {
  lastSnapshot.value = cloneQuestionData();
  questionData.images = questionData.images.filter((image) => image.id !== id);
  ElMessage.success('图片已移除');
}

function handleRegionSelected(region: RegionSelection) {
  ElMessage.info(`已框选第 ${region.page_num} 页区域；OCR 写入将在下一步接入。`);
}

function handleUndo() {
  if (!lastSnapshot.value) return;
  restoreQuestionData(lastSnapshot.value);
  lastSnapshot.value = null;
  ElMessage.success('已撤销最近一次识别修复');
}

function buildQuestionPayload(needsReview = selectedQuestion.value?.needs_review ?? true) {
  const images = questionData.images.map((image) => ({
    ...(image.meta || {}),
    url: image.src,
    ref: image.id,
    caption: image.name,
    role: image.slot,
    image_role: image.slot === 'options' ? 'option_image' : 'question_visual',
    insert_position: image.slot === 'options' ? 'below_options' : 'below_stem',
  }));
  return {
    content: cleanQuestionText(questionData.stem),
    option_a: questionData.options.find((option) => option.key === 'A')?.text || '',
    option_b: questionData.options.find((option) => option.key === 'B')?.text || '',
    option_c: questionData.options.find((option) => option.key === 'C')?.text || '',
    option_d: questionData.options.find((option) => option.key === 'D')?.text || '',
    answer: selectedQuestion.value?.answer || '',
    analysis: selectedQuestion.value?.analysis || '',
    images,
    status: 'draft' as const,
    needs_review: needsReview,
  };
}

async function manualSave() {
  if (!selectedQuestion.value) return;
  const shouldContinue = await confirmUnresolvedAiRisks('保存草稿');
  if (!shouldContinue) return;
  saveState.value = 'saving';
  window.clearTimeout(saveTimer);
  saving.value = true;
  try {
    await updateQuestion(selectedQuestion.value.id, buildQuestionPayload(true));
    await loadQuestion(selectedQuestion.value.id);
    ElMessage.success('题干草稿已保存');
  } finally {
    saving.value = false;
  }
}

async function markNeedsReview() {
  if (!selectedQuestion.value) return;
  saving.value = true;
  try {
    await updateQuestion(selectedQuestion.value.id, buildQuestionPayload(true));
    await loadQuestion(selectedQuestion.value.id);
    ElMessage.success('已标记为需复核');
  } finally {
    saving.value = false;
  }
}

async function markStemReviewed() {
  if (!selectedQuestion.value) return;
  const shouldContinue = await confirmUnresolvedAiRisks('题干审核通过');
  if (!shouldContinue) return;
  saving.value = true;
  try {
    await updateQuestion(selectedQuestion.value.id, buildQuestionPayload(false));
    await loadQuestion(selectedQuestion.value.id);
    ElMessage.success('题干审核通过，等待答案匹配');
  } finally {
    saving.value = false;
  }
}

async function handleAcceptAiSuggestion(scope: 'answer' | 'analysis' | 'both') {
  if (!selectedQuestion.value) return;
  const action = aiActionForScope(scope);
  if (!action) return;
  const label = scope === 'answer' ? 'AI 答案' : scope === 'analysis' ? 'AI 解析' : 'AI 答案和解析';
  await ElMessageBox.confirm(`确认用${label}覆盖当前题目的对应字段？此操作不会自动发布题目。`, '采纳 AI 建议', {
    type: aiSolverAssist.value.conflict || aiSolverAssist.value.lowConfidence ? 'warning' : 'info',
    confirmButtonText: '确认采纳',
    cancelButtonText: '取消',
  });
  aiAccepting.value = scope;
  try {
    const detail = await applyQuestionAiAction(selectedQuestion.value.id, action);
    selectedQuestion.value = detail;
    replaceQuestionInList(detail);
    hydrateQuestionData(detail);
    ElMessage.success(`已采纳${label}`);
  } finally {
    aiAccepting.value = '';
  }
}

async function handleIgnoreAiSuggestion() {
  if (!selectedQuestion.value) return;
  await ElMessageBox.confirm('确认忽略当前 AI 建议？该操作只记录审计日志，不会修改答案或解析。', '忽略 AI 建议', {
    type: 'warning',
    confirmButtonText: '确认忽略',
    cancelButtonText: '取消',
  });
  aiAccepting.value = 'ignore';
  try {
    const detail = await applyQuestionAiAction(selectedQuestion.value.id, 'ignore_ai_suggestion');
    selectedQuestion.value = detail;
    replaceQuestionInList(detail);
    hydrateQuestionData(detail);
    ElMessage.success('已记录忽略 AI 建议');
  } finally {
    aiAccepting.value = '';
  }
}

async function confirmUnresolvedAiRisks(actionLabelText: string) {
  const risky = unresolvedAiRiskQuestions.value;
  if (!risky.length) return true;
  try {
    await ElMessageBox.confirm(
      `当前试卷还有 ${risky.length} 道 AI 风险题未处理，是否继续${actionLabelText}？`,
      'AI 风险未处理',
      {
        type: 'warning',
        confirmButtonText: '继续',
        cancelButtonText: '返回处理',
      },
    );
    return true;
  } catch {
    return false;
  }
}

function aiActionForScope(scope: 'answer' | 'analysis' | 'both'): QuestionAiAction | '' {
  if (scope === 'answer') return aiSolverAssist.value.answer ? 'accept_ai_answer' : '';
  if (scope === 'analysis') return aiSolverAssist.value.analysis ? 'accept_ai_analysis' : '';
  return aiSolverAssist.value.answer || aiSolverAssist.value.analysis ? 'accept_ai_both' : '';
}

function aiActionLabel(action: string) {
  return {
    accept_ai_answer: '接受 AI 答案',
    accept_ai_analysis: '接受 AI 解析',
    accept_ai_both: '同时接受答案和解析',
    ignore_ai_suggestion: '忽略 AI 建议',
  }[action] || action;
}

function formatActionTime(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

onMounted(fetchBanks);
</script>

<style scoped>
.workbench-page {
  display: flex;
  height: calc(100vh - 56px);
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  background: #eef2f7;
  color: #111827;
}

.workbench-header {
  display: flex;
  height: 72px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #dbe2ee;
  background: #fbfcff;
  padding: 0 18px;
}

.title-group,
.header-actions,
.header-meta {
  display: flex;
  align-items: center;
}

.title-group {
  gap: 12px;
}

.back-button {
  flex: 0 0 auto;
}

h1 {
  margin: 0 0 7px;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0;
}

.header-meta {
  gap: 10px;
}

.save-state {
  font-size: 12px;
}

.save-state.saving {
  color: #b45309;
}

.save-state.saved {
  color: #047857;
}

.save-state.idle {
  color: #64748b;
}

.header-actions {
  gap: 8px;
}

.bank-search {
  width: 260px;
}

.bank-picker-main {
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding: 18px;
}

.bank-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.bank-card,
.bank-skeleton {
  min-height: 210px;
  border: 1px solid #dbe2ee;
  border-radius: 14px;
  background: #fbfcff;
  padding: 16px;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.06);
}

.bank-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
}

.bank-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.bank-card h2 {
  margin: 0 0 7px;
  color: #111827;
  font-size: 17px;
  font-weight: 760;
  line-height: 1.35;
}

.bank-card p {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.bank-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.bank-metrics span {
  display: grid;
  gap: 4px;
  min-width: 0;
  border: 1px solid #e3e9f3;
  border-radius: 10px;
  background: #f6f8fc;
  color: #64748b;
  font-size: 12px;
  padding: 10px;
}

.bank-metrics strong {
  overflow: hidden;
  color: #111827;
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bank-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.workbench-main {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  gap: 12px;
  padding: 12px;
}

.pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #dbe2ee;
  border-radius: 14px;
  background: #fbfcff;
}

.pdf-pane,
.editor-pane {
  flex: 4 1 0;
}

.preview-pane {
  flex: 3 1 0;
}

.pane-head {
  display: flex;
  min-height: 58px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #e4eaf3;
  padding: 12px 14px;
}

.pane-head div {
  display: grid;
  gap: 3px;
}

.pane-head strong {
  font-size: 14px;
}

.pane-head span {
  color: #64748b;
  font-size: 12px;
}

.real-pdf-shell {
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
  padding: 14px;
}

.real-pdf-shell :deep(.pdf-locator) {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

.real-pdf-shell :deep(.pdf-viewport) {
  min-height: 0;
  flex: 1 1 auto;
}

.pdf-missing {
  display: grid;
  height: 100%;
  min-height: 320px;
  place-content: center;
  gap: 8px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #f8fafc;
  color: #64748b;
  text-align: center;
}

.pdf-missing strong {
  color: #111827;
  font-size: 15px;
}

.editor-form {
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding: 14px;
}

.stage-note {
  margin: 0 0 14px;
  border: 1px solid #dbe6f5;
  border-radius: 10px;
  background: #f4f8ff;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 12px;
}

.paper-question-queue {
  display: grid;
  gap: 10px;
  margin: 0 0 14px;
  border: 1px solid #dbe2ee;
  border-radius: 12px;
  background: #fbfcff;
  padding: 12px;
}

.queue-head {
  display: grid;
  gap: 10px;
}

.queue-head > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.queue-head strong {
  color: #111827;
  font-size: 14px;
}

.queue-head span {
  color: #64748b;
  font-size: 12px;
}

.queue-filters,
.queue-ai-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.queue-filters button {
  min-height: 28px;
  border: 1px solid #dbe2ee;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 10px;
}

.queue-filters button.active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 700;
}

.queue-list {
  display: grid;
  max-height: 260px;
  overflow: auto;
  gap: 8px;
}

.queue-question {
  display: grid;
  gap: 8px;
  width: 100%;
  border: 1px solid #e1e8f2;
  border-radius: 10px;
  background: #ffffff;
  cursor: pointer;
  padding: 10px;
  text-align: left;
}

.queue-question:hover,
.queue-question.active {
  border-color: #2563eb;
  background: #f4f8ff;
}

.queue-question.risk:not(.active) {
  border-color: #fed7aa;
  background: #fffaf2;
}

.queue-question-main {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 7px;
  color: #334155;
  font-size: 13px;
  line-height: 1.5;
}

.queue-question-main strong {
  color: #111827;
}

.queue-tag {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  border: 1px solid #dbe2ee;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  line-height: 1.2;
  padding: 2px 7px;
}

.queue-tag.candidate {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.queue-tag.danger {
  border-color: #fecaca;
  background: #fff1f2;
  color: #b91c1c;
}

.queue-tag.warning {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #b45309;
}

.queue-tag.muted {
  color: #64748b;
}

.queue-tag.model {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-answer-panel {
  display: grid;
  gap: 8px;
  margin: 0 0 14px;
  border: 1px solid #dbe2ee;
  border-radius: 10px;
  background: #ffffff;
  padding: 10px 12px;
}

.current-answer-panel div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.current-answer-panel span {
  color: #64748b;
  font-size: 12px;
}

.current-answer-panel strong {
  color: #111827;
  font-size: 16px;
}

.current-answer-panel p {
  margin: 0;
  color: #334155;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.ai-assist-panel {
  display: grid;
  gap: 10px;
  margin: 0 0 14px;
  border: 1px solid #bfe3d0;
  border-radius: 10px;
  background: #f2fbf6;
  padding: 10px 12px;
}

.ai-preaudit-panel {
  display: grid;
  gap: 12px;
  margin: 0 0 14px;
  border: 1px solid #bae6fd;
  border-radius: 12px;
  background: #f0f9ff;
  padding: 12px;
}

.ai-preaudit-panel.status-warning,
.ai-preaudit-panel.status-failed,
.ai-preaudit-panel.status-skipped {
  border-color: #fed7aa;
  background: #fff7ed;
}

.ai-preaudit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.ai-preaudit-head > div {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.ai-preaudit-grid {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 8px 12px;
}

.ai-preaudit-grid span {
  color: #64748b;
  font-size: 12px;
}

.ai-preaudit-grid p {
  margin: 0;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.ai-assist-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.ai-assist-head strong {
  color: #14532d;
  font-size: 14px;
}

.ai-assist-head > div {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.ai-assist-panel p {
  margin: 0;
  color: #315044;
  font-size: 13px;
  line-height: 1.55;
}

.ai-assist-grid {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  gap: 7px 10px;
  color: #315044;
  font-size: 13px;
}

.ai-assist-grid span {
  color: #547066;
}

.ai-corrections {
  display: grid;
  gap: 6px;
}

.ai-correction-row {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: #315044;
  font-size: 12px;
}

.ai-correction-row small {
  overflow: hidden;
  color: #64756e;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-solver-panel {
  display: grid;
  gap: 10px;
  margin: 0 0 14px;
  border: 1px solid #c9d7ee;
  border-radius: 10px;
  background: #f6f9ff;
  padding: 10px 12px;
}

.ai-solver-panel.conflict {
  border-color: #fecaca;
  background: #fff7f7;
}

.ai-solver-panel.caution:not(.conflict) {
  border-color: #fed7aa;
  background: #fffaf2;
}

.ai-solver-panel.ignored {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.ai-solver-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.ai-solver-head strong {
  color: #1e3a8a;
  font-size: 14px;
}

.ai-solver-head > div,
.ai-tag-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.ai-solver-grid {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  align-items: start;
  gap: 8px 10px;
  color: #334155;
  font-size: 13px;
}

.ai-solver-grid > span {
  color: #64748b;
}

.ai-solver-grid p,
.ai-solver-panel > p {
  margin: 0;
  color: #334155;
  line-height: 1.55;
}

.ai-answer-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.answer-box {
  display: grid;
  gap: 5px;
  min-width: 0;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  background: #ffffff;
  padding: 10px;
}

.answer-box span {
  color: #64748b;
  font-size: 12px;
}

.answer-box strong {
  color: #0f172a;
  font-size: 18px;
}

.answer-box.candidate {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.ai-analysis-collapse {
  border: 0;
}

.ai-analysis-text {
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.ai-accept-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-audit-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  border-top: 1px solid #dbe4f0;
  color: #64748b;
  font-size: 12px;
  padding-top: 8px;
}

.ai-audit-line strong {
  color: #0f172a;
}

.ai-action-history {
  display: grid;
  gap: 6px;
  border-top: 1px solid #dbe4f0;
  padding-top: 8px;
}

.ai-action-history > strong {
  color: #0f172a;
  font-size: 13px;
}

.ai-history-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #64748b;
  font-size: 12px;
}

.ai-history-row span {
  color: #334155;
  font-weight: 650;
}

.image-editor {
  display: grid;
  gap: 10px;
  margin: 0 0 18px;
  border: 1px solid #e1e8f2;
  border-radius: 12px;
  background: #f8fafc;
  padding: 12px;
}

.field-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.field-head div:first-child {
  display: grid;
  gap: 4px;
}

.field-head strong {
  color: #111827;
  font-size: 14px;
}

.field-head span {
  color: #64748b;
  font-size: 12px;
}

.image-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.slot-select {
  width: 142px;
}

.hidden-file-input {
  display: none;
}

.image-empty {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 92px;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  color: #64748b;
  cursor: pointer;
  font-size: 13px;
  line-height: 1.6;
  padding: 18px 20px;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    color 160ms ease;
}

.image-empty:hover,
.image-empty:focus-visible {
  border-color: #2563eb;
  background: #eef5ff;
  color: #1d4ed8;
  outline: none;
}

.image-empty .el-icon {
  color: #2563eb;
  font-size: 24px;
}

.image-empty div {
  display: grid;
  gap: 3px;
}

.image-empty strong {
  color: #273449;
  font-size: 14px;
  font-weight: 720;
}

.image-empty span {
  color: inherit;
}

.image-list {
  display: grid;
  gap: 10px;
}

.image-item {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr) 32px;
  align-items: center;
  gap: 10px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fbfcff;
  padding: 8px;
}

.image-item img {
  width: 74px;
  height: 54px;
  border-radius: 8px;
  object-fit: cover;
  background: #e8edf5;
}

.image-meta {
  display: grid;
  min-width: 0;
  gap: 7px;
}

.image-meta strong {
  overflow: hidden;
  color: #273449;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.option-editor {
  display: grid;
  gap: 10px;
  margin: 4px 0 18px;
}

.option-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.phone-wrap {
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  place-items: center;
  overflow: auto;
  padding: 18px;
  background:
    radial-gradient(circle at 26% 12%, rgba(37, 99, 235, 0.11), transparent 28%),
    linear-gradient(180deg, #f6f8fc 0%, #e9eef6 100%);
}

.phone-frame {
  position: relative;
  width: min(288px, 100%);
  height: min(620px, 100%);
  min-height: 540px;
  border: 10px solid #172033;
  border-radius: 36px;
  background: #172033;
  box-shadow: 0 24px 52px rgba(15, 23, 42, 0.22);
}

.phone-speaker {
  position: absolute;
  top: 12px;
  left: 50%;
  width: 72px;
  height: 5px;
  transform: translateX(-50%);
  border-radius: 99px;
  background: #334155;
}

.phone-screen {
  height: 100%;
  overflow: auto;
  border-radius: 26px;
  background: #f8fafc;
  padding: 36px 16px 18px;
}

.phone-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
  color: #64748b;
  font-size: 12px;
}

.phone-status strong {
  color: #2563eb;
}

.phone-ai-audit {
  display: grid;
  gap: 5px;
  margin: 0 0 12px;
  border: 1px solid #fed7aa;
  border-radius: 12px;
  background: #fff7ed;
  padding: 10px;
  color: #7c2d12;
  font-size: 12px;
  line-height: 1.45;
}

.phone-ai-audit strong {
  color: #9a3412;
}

.phone-screen h2 {
  margin: 0;
  color: #111827;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.65;
}

.phone-images {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.phone-images img {
  width: 100%;
  max-height: 180px;
  border: 1px solid #dce3ee;
  border-radius: 12px;
  object-fit: cover;
  background: #eef2f7;
}

.phone-options {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.phone-option {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
  border: 1px solid #dce3ee;
  border-radius: 12px;
  background: #fffefa;
  padding: 12px;
}

.phone-option span {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 50%;
  background: #e8edf5;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

.phone-option p {
  margin: 0;
  color: #273449;
  font-size: 13px;
  line-height: 1.65;
}
</style>
