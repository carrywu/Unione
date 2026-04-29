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
              <el-button type="primary" @click="enterWorkbench(bank.id)">题干审核</el-button>
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
            <el-tag effect="plain" type="info">题干审核</el-tag>
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
            <strong>题干结构审核</strong>
            <span>只校对题干、选项、图片和定位，答案后续匹配</span>
          </div>
        </div>

        <el-form class="editor-form" label-position="top">
          <div class="stage-note">
            当前阶段不录入正确答案，题干通过后仍保留草稿状态，等待答案册匹配后再发布练习。
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
              <h2>{{ questionData.stem }}</h2>
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
                  <p>{{ option.text }}</p>
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
import { ElMessage } from 'element-plus';
import { ArrowLeft, Delete, DocumentChecked, Picture, Plus, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue';
import { getBanks, type Bank } from '@/api/bank';
import { pdfProxyUrl } from '@/api/pdf';
import { getQuestion, getQuestions, updateQuestion, type Question } from '@/api/question';
import PdfLocator from '@/components/PdfLocator.vue';

type OptionKey = 'A' | 'B' | 'C' | 'D';
type ImageSlot = 'stem' | 'options';

interface QuestionOption {
  key: OptionKey;
  text: string;
}

interface QuestionImage {
  id: string;
  name: string;
  src: string;
  slot: ImageSlot;
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
const banks = ref<Bank[]>([]);
const questions = ref<Question[]>([]);
const selectedQuestion = ref<Question | null>(null);
const bankKeyword = ref('');
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

let saveTimer: number | undefined;
let hydratingQuestion = false;

const saveStateText = computed(() => {
  if (saveState.value === 'saving') return '保存中...';
  if (saveState.value === 'saved') return '已保存';
  return '有未保存修改';
});

const sourcePage = computed(() => selectedQuestion.value?.pdf_source?.page_num || selectedQuestion.value?.page_num || selectedQuestion.value?.page_range?.[0] || 1);
const pdfLocatorSrc = computed(() => {
  const taskId = selectedQuestion.value?.pdf_source?.task_id;
  return taskId ? pdfProxyUrl(taskId) : selectedQuestion.value?.pdf_source?.file_url || '';
});
const pdfRequestHeaders = computed(() => {
  const token = localStorage.getItem('admin_token');
  return token ? { Authorization: `Bearer ${token}` } : undefined;
});
const pdfHighlights = computed(() => {
  const bbox = selectedQuestion.value?.pdf_source?.source_bbox || selectedQuestion.value?.source_bbox;
  if (!bbox || bbox.length !== 4) return [];
  const page = selectedQuestion.value?.pdf_source?.source_page_start || selectedQuestion.value?.source_page_start || sourcePage.value;
  return [
    {
      page: Math.max(1, Number(page) || 1),
      x: bbox[0],
      y: bbox[1],
      width: Math.max(1, bbox[2] - bbox[0]),
      height: Math.max(1, bbox[3] - bbox[1]),
      label: '题目区域',
    },
  ];
});

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
    const result = await getQuestions({ bankId, page: 1, pageSize: 100 });
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
  hydrateQuestionData(detail);
  currentPdfPage.value = Math.max(1, Number(sourcePage.value) || 1);
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
  return String(value || '')
    .split(/\r?\n/)
    .filter((line) => !['【', '】', '【】'].includes(line.trim()))
    .join('\n')
    .replace(/^[\s\r\n]*[【】]+[\s\r\n]*/g, '')
    .replace(/[\s\r\n]*[【】]+[\s\r\n]*$/g, '')
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
      const src = image.url || (image.base64 ? `data:image/png;base64,${image.base64}` : '');
      return {
        id: image.ref || `image-${index}`,
        name: image.caption || image.ref || `题目图片 ${index + 1}`,
        src,
        slot: 'stem' as ImageSlot,
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
    url: image.src,
    ref: image.id,
    caption: image.name,
    role: image.slot,
  }));
  return {
    content: cleanQuestionText(questionData.stem),
    option_a: questionData.options.find((option) => option.key === 'A')?.text || '',
    option_b: questionData.options.find((option) => option.key === 'B')?.text || '',
    option_c: questionData.options.find((option) => option.key === 'C')?.text || '',
    option_d: questionData.options.find((option) => option.key === 'D')?.text || '',
    answer: '',
    analysis: '',
    images,
    status: 'draft' as const,
    needs_review: needsReview,
  };
}

async function manualSave() {
  if (!selectedQuestion.value) return;
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
  saving.value = true;
  try {
    await updateQuestion(selectedQuestion.value.id, buildQuestionPayload(false));
    await loadQuestion(selectedQuestion.value.id);
    ElMessage.success('题干审核通过，等待答案匹配');
  } finally {
    saving.value = false;
  }
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
