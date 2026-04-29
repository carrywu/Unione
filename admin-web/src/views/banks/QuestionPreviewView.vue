<template>
  <div class="page preview-page">
    <PageHeader />

    <div class="toolbar">
      <el-button @click="router.push(`/banks/${bankId}/questions`)">返回列表</el-button>
      <el-button type="primary" @click="router.push(`/banks/${bankId}/review?questionId=${questionId}`)">
        进入审核
      </el-button>
      <el-button v-if="question" type="primary" :loading="saving" @click="handleSave">保存修改</el-button>
      <el-button v-if="question" type="success" :loading="publishing" @click="handlePublish">保存并通过</el-button>
      <el-button v-if="question" :loading="aiReviewLoading" @click="handleAiReview">AI预审</el-button>
      <el-button v-if="question" :disabled="!lastUndo" @click="handleUndo">撤销最近修复</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="10" animated />
    <el-empty v-else-if="!question" description="题目不存在" />

    <div v-else class="preview-layout">
      <el-form class="question-surface" label-position="top" :model="form">
        <div class="question-head">
          <div>
            <div class="question-index">第 {{ form.index_num }} 题</div>
            <div class="question-meta">
              <el-tag size="small">{{ form.type === 'judge' ? '判断题' : '单选题' }}</el-tag>
              <StatusTag :status="form.status" :needs-review="form.needs_review" />
              <el-tag v-if="question.page_range?.length" size="small" type="info">
                {{ question.page_range.join(' - ') }} 页
              </el-tag>
            </div>
          </div>
          <el-tag v-if="question.parse_confidence != null" :type="confidenceType">
            置信度 {{ (question.parse_confidence * 100).toFixed(0) }}%
          </el-tag>
        </div>

        <section v-if="question.material?.content || materialImages.length" class="preview-section">
          <h2>材料</h2>
          <p v-if="question.material?.content" class="material-text">{{ question.material.content }}</p>
          <ImageGallery
            v-if="materialImages.length"
            :images="materialImages"
            target="material"
            :pending-replacement="pendingImageReplacement"
            @replace="prepareImageReplacement"
            @delete="deleteImage"
          />
        </section>

        <section class="preview-section">
          <h2>题干</h2>
          <el-form-item label="">
            <el-input v-model="form.content" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" @input="dirty = true" />
          </el-form-item>
          <ImageGallery
            v-if="questionImages.length"
            :images="questionImages"
            target="question"
            :pending-replacement="pendingImageReplacement"
            @replace="prepareImageReplacement"
            @delete="deleteImage"
          />
          <el-empty v-else description="该题暂无图片" :image-size="56" />
        </section>

        <section v-if="form.type !== 'judge'" class="preview-section">
          <h2>选项</h2>
          <div class="option-list">
            <div v-for="option in options" :key="option.key" class="option-row">
              <span class="option-key">{{ option.key }}</span>
              <el-input
                v-model="form[`option_${option.key.toLowerCase()}`]"
                type="textarea"
                autosize
                placeholder="未填写"
                @input="dirty = true"
              />
            </div>
          </div>
        </section>

        <section class="preview-section answer-section">
          <div>
            <h2>答案</h2>
            <el-select v-model="form.answer" class="full" placeholder="选择答案" @change="dirty = true">
              <template v-if="form.type === 'judge'">
                <el-option label="对" value="对" />
                <el-option label="错" value="错" />
              </template>
              <template v-else>
                <el-option v-for="key in optionKeys" :key="key" :label="key" :value="key" />
              </template>
            </el-select>
          </div>
          <div>
            <h2>解析</h2>
            <el-input v-model="form.analysis" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="暂无解析" @input="dirty = true" />
            <div v-if="question.analysis_image_url" class="answer-image">
              <ImagePreview :src="question.analysis_image_url" />
            </div>
          </div>
        </section>

        <section class="preview-section state-section">
          <div>
            <h2>审核状态</h2>
            <el-radio-group v-model="form.status" @change="dirty = true">
              <el-radio-button label="draft">草稿</el-radio-button>
              <el-radio-button label="published">已发布</el-radio-button>
            </el-radio-group>
          </div>
          <el-checkbox v-model="form.needs_review" @change="dirty = true">仍需复查</el-checkbox>
        </section>

        <section v-if="readabilityReview" class="preview-section">
          <h2>AI预审</h2>
          <el-alert
            :title="readabilityReview.needs_review ? '当前题目需要重新框选或复查' : '当前题目基本可读'"
            :type="readabilityReview.needs_review ? 'warning' : 'success'"
            :closable="false"
            show-icon
          />
          <div class="ai-review-meta">
            <el-tag size="small" :type="readabilityReview.score >= 0.8 ? 'success' : 'warning'">
              可读性 {{ Math.round((readabilityReview.score || 0) * 100) }}%
            </el-tag>
            <el-tag v-for="area in readabilityReview.focus_areas" :key="area" size="small" type="info">
              {{ focusAreaText(area) }}
            </el-tag>
          </div>
          <ul v-if="readabilityReview.reasons.length" class="ai-review-list">
            <li v-for="reason in readabilityReview.reasons" :key="reason">{{ reason }}</li>
          </ul>
          <div v-if="readabilityReview.prompts.length" class="ai-review-actions">
            <el-tag v-for="prompt in readabilityReview.prompts" :key="prompt" type="warning">
              {{ prompt }}
            </el-tag>
          </div>
        </section>
      </el-form>

      <aside class="source-panel">
        <section class="pdf-panel">
          <div class="pdf-head">
            <div>
              <h2>PDF定位</h2>
              <div class="pdf-file">{{ question.pdf_source?.file_name || '原始 PDF' }}</div>
            </div>
            <el-button v-if="question.pdf_source?.file_url" link type="primary" @click="openPdf">
              新窗口打开
            </el-button>
          </div>

          <div v-if="question.pdf_source?.file_url" class="pdf-controls">
            <el-button size="small" type="primary" @click="resetPdfPage">回到题目页</el-button>
            <el-button size="small" :type="regionMode ? 'warning' : 'default'" @click="regionMode = !regionMode">
              {{ regionMode ? '退出框选识别' : '框选识别' }}
            </el-button>
          </div>

          <PdfLocator
            v-if="question.pdf_source?.file_url"
            v-model:page="currentPdfPage"
            :src="pdfLocatorSrc"
            :open-src="question.pdf_source.file_url"
            :headers="pdfRequestHeaders"
            :highlights="pdfHighlights"
            :selection-enabled="regionMode"
            @region-selected="handleRegionSelected"
          />
          <el-empty v-else description="该题没有解析任务来源，无法定位原 PDF" :image-size="64" />
        </section>

        <section class="info-block">
          <h2>解析信息</h2>
          <dl>
            <div>
              <dt>题目 ID</dt>
              <dd>{{ question.id }}</dd>
            </div>
            <div>
              <dt>解析任务</dt>
              <dd>{{ question.parse_task_id || '-' }}</dd>
            </div>
            <div>
              <dt>答案来源</dt>
              <dd>{{ question.answer_source_id || '-' }}</dd>
            </div>
            <div>
              <dt>匹配置信度</dt>
              <dd>
                <el-tag v-if="question.analysis_match_confidence != null" size="small" type="success">
                  {{ question.analysis_match_confidence }}
                </el-tag>
                <span v-else>-</span>
              </dd>
            </div>
            <div>
              <dt>定位页码</dt>
              <dd>
                <el-tag v-if="question.page_num" size="small" type="info">第 {{ question.page_num }} 页</el-tag>
                <el-tag v-if="question.page_range?.length" size="small" type="info">{{ question.page_range.join(' - ') }} 页</el-tag>
                <span v-if="!question.page_num && !question.page_range?.length">-</span>
              </dd>
            </div>
            <div>
              <dt>图片引用</dt>
              <dd>
                <el-tag v-for="ref in question.image_refs || []" :key="ref" size="small" type="info">{{ ref }}</el-tag>
                <span v-if="!question.image_refs?.length">-</span>
              </dd>
            </div>
            <div>
              <dt>解析警告</dt>
              <dd>
                <el-tag v-for="warning in question.parse_warnings || []" :key="warning" size="small" type="danger">
                  {{ warning }}
                </el-tag>
                <span v-if="!question.parse_warnings?.length">-</span>
              </dd>
            </div>
          </dl>
        </section>

        <section v-if="question.raw_text" class="info-block">
          <h2>原始文本</h2>
          <pre>{{ question.raw_text }}</pre>
        </section>
      </aside>
    </div>

    <el-dialog v-model="actionDialogVisible" title="框选识别" width="460px">
      <el-alert
        v-if="pendingImageReplacement"
        class="region-alert"
        :title="`将当前框选区域替换为${pendingImageReplacement.target === 'material' ? '材料' : '题目'}图片 #${pendingImageReplacement.index + 1}`"
        type="warning"
        :closable="false"
        show-icon
      />
      <div class="region-actions">
        <el-button :loading="ocrLoading" @click="runRegionOcr('stem')">识别为题干</el-button>
        <el-button :loading="ocrLoading" @click="runRegionOcr('options')">识别为选项</el-button>
        <el-button :loading="ocrLoading" @click="runRegionOcr('material')">识别为材料</el-button>
        <el-button :loading="ocrLoading" @click="runRegionOcr('analysis')">识别为解析</el-button>
        <el-button v-if="pendingImageReplacement" type="warning" :loading="ocrLoading" @click="replaceSelectedImage">
          替换选中图片
        </el-button>
        <el-button :loading="ocrLoading" @click="saveRegionImage('question')">保存为题目图片</el-button>
        <el-button :loading="ocrLoading" :disabled="!question?.material?.id" @click="saveRegionImage('material')">
          保存为材料图片
        </el-button>
      </div>
      <template #footer>
        <el-button @click="actionDialogVisible = false">忽略该区域</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="ocrDialogVisible" :title="ocrDialogTitle" width="720px">
      <div class="ocr-review">
        <el-alert
          v-if="ocrResult"
          :title="`来源：${ocrSourceText}，置信度 ${Math.round((ocrResult.confidence || 0) * 100)}%`"
          type="info"
          :closable="false"
          show-icon
        />
        <template v-if="activeOcrMode === 'options'">
          <div v-for="key in optionKeys" :key="key" class="ocr-option-row">
            <span class="option-key">{{ key }}</span>
            <el-input v-model="ocrOptions[key]" type="textarea" autosize placeholder="未识别" />
          </div>
        </template>
        <template v-else>
          <div class="ocr-diff">
            <div>
              <h3>当前内容</h3>
              <pre>{{ currentFieldValue }}</pre>
            </div>
            <div>
              <h3>识别结果</h3>
              <el-input v-model="ocrText" type="textarea" :autosize="{ minRows: 8, maxRows: 18 }" />
            </div>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="ocrDialogVisible = false">取消</el-button>
        <el-button v-if="activeOcrMode !== 'options'" :loading="applyingOcr" @click="applyOcr('append')">追加</el-button>
        <el-button type="primary" :loading="applyingOcr" @click="applyOcr('replace')">替换</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElButton, ElMessage, ElMessageBox } from 'element-plus';
import { computed, defineComponent, h, onMounted, reactive, ref, type PropType } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ocrPdfRegion, pdfProxyUrl, type OcrRegionMode, type OcrRegionResult } from '@/api/pdf';
import { updateMaterial } from '@/api/material';
import {
  getQuestion,
  reviewQuestionReadability,
  updateQuestion,
  type Question,
  type ReadabilityReviewResult,
} from '@/api/question';
import ImagePreview from '@/components/ImagePreview.vue';
import PageHeader from '@/components/PageHeader.vue';
import PdfLocator from '@/components/PdfLocator.vue';
import StatusTag from '@/components/StatusTag.vue';

type PreviewImage = {
  src: string;
  ref?: string;
  caption?: string;
  role?: string;
  bbox?: number[];
  source?: string;
  assignmentConfidence?: number;
};

type ImageTarget = 'question' | 'material';

type PendingImageReplacement = {
  target: ImageTarget;
  index: number;
};

type RegionSelection = {
  page_num: number;
  bbox: [number, number, number, number];
  viewport_width: number;
  viewport_height: number;
  pdf_width: number;
  pdf_height: number;
  scale: number;
};

const ImageGallery = defineComponent({
  props: {
    images: {
      type: Array<PreviewImage>,
      required: true,
    },
    target: {
      type: String as PropType<ImageTarget>,
      required: true,
    },
    pendingReplacement: {
      type: Object as PropType<PendingImageReplacement | null>,
      default: null,
    },
  },
  emits: ['replace', 'delete'],
  setup(props, { emit }) {
    return () =>
      h(
        'div',
        { class: 'image-gallery' },
        props.images.map((image, index) =>
          h('div', {
            class: [
              'preview-image-item',
              props.pendingReplacement?.target === props.target && props.pendingReplacement.index === index
                ? 'pending-replace'
                : '',
            ],
            key: `${image.src}-${index}`,
          }, [
            h(ImagePreview, { src: image.src }),
            h('div', { class: 'image-caption' }, [
              image.ref ? h('span', { class: 'image-pill' }, image.ref) : null,
              image.role ? h('span', { class: 'image-pill muted' }, image.role) : null,
              image.assignmentConfidence != null
                ? h('span', { class: 'image-pill muted' }, `${Math.round(image.assignmentConfidence * 100)}%`)
                : null,
              image.caption ? h('span', image.caption) : null,
            ]),
            h('div', { class: 'image-actions' }, [
              h(
                ElButton,
                {
                  size: 'small',
                  type: 'primary',
                  link: true,
                  onClick: () => emit('replace', props.target, index),
                },
                () => '框选替换',
              ),
              h(
                ElButton,
                {
                  size: 'small',
                  type: 'danger',
                  link: true,
                  onClick: () => emit('delete', props.target, index),
                },
                () => '删除',
              ),
            ]),
          ]),
        ),
      );
  },
});

const route = useRoute();
const router = useRouter();
const bankId = String(route.params.id);
const questionId = String(route.params.questionId);
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const aiReviewLoading = ref(false);
const dirty = ref(false);
const question = ref<Question | null>(null);
const readabilityReview = ref<ReadabilityReviewResult | null>(null);
const currentPdfPage = ref(1);
const regionMode = ref(false);
const actionDialogVisible = ref(false);
const ocrDialogVisible = ref(false);
const ocrLoading = ref(false);
const applyingOcr = ref(false);
const selectedRegion = ref<RegionSelection | null>(null);
const pendingImageReplacement = ref<PendingImageReplacement | null>(null);
const activeOcrMode = ref<OcrRegionMode>('stem');
const ocrResult = ref<OcrRegionResult | null>(null);
const ocrText = ref('');
const ocrOptions = reactive<Record<string, string>>({ A: '', B: '', C: '', D: '' });
const lastUndo = ref<null | { label: string; apply: () => Promise<void> }>(null);
const optionKeys = ['A', 'B', 'C', 'D'];
const form = reactive<Partial<Question> & Record<string, any>>({});

const confidenceType = computed(() => {
  const confidence = question.value?.parse_confidence;
  if (confidence == null) return 'info';
  if (confidence >= 0.8) return 'success';
  if (confidence >= 0.5) return 'warning';
  return 'danger';
});

const options = computed(() => [
  { key: 'A' },
  { key: 'B' },
  { key: 'C' },
  { key: 'D' },
]);

const questionImages = computed(() => normalizeImageList(question.value?.images || []));
const materialImages = computed(() => normalizeImageList(question.value?.material?.images || []));
const sourcePage = computed(() => question.value?.pdf_source?.page_num || question.value?.page_num || question.value?.page_range?.[0] || 1);
const pdfLocatorSrc = computed(() => {
  const taskId = question.value?.pdf_source?.task_id;
  return taskId ? pdfProxyUrl(taskId) : question.value?.pdf_source?.file_url || '';
});
const pdfViewerSrc = computed(() => {
  const url = question.value?.pdf_source?.file_url;
  if (!url) return '';
  return `${url}#page=${currentPdfPage.value}`;
});
const pdfRequestHeaders = computed(() => {
  const token = localStorage.getItem('admin_token');
  return token ? { Authorization: `Bearer ${token}` } : undefined;
});
const pdfHighlights = computed(() => {
  const bbox = question.value?.pdf_source?.source_bbox || question.value?.source_bbox;
  if (!bbox || bbox.length !== 4) return [];
  const page = question.value?.pdf_source?.source_page_start || question.value?.source_page_start || sourcePage.value;
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
const ocrDialogTitle = computed(() => {
  return {
    stem: '确认题干识别结果',
    options: '确认选项识别结果',
    material: '确认材料识别结果',
    analysis: '确认解析识别结果',
    image: '确认图片',
  }[activeOcrMode.value];
});
const ocrSourceText = computed(() => {
  return {
    pdf_text_layer: 'PDF 文本层',
    vision_model: '视觉识别',
    manual_crop: '截图',
  }[ocrResult.value?.source || ''] || ocrResult.value?.source || '-';
});
const currentFieldValue = computed(() => {
  if (activeOcrMode.value === 'stem') return form.content || '';
  if (activeOcrMode.value === 'analysis') return form.analysis || '';
  if (activeOcrMode.value === 'material') return question.value?.material?.content || '';
  return '';
});

async function fetchQuestion() {
  loading.value = true;
  try {
    fillQuestion(await getQuestion(questionId));
    resetPdfPage();
  } finally {
    loading.value = false;
  }
}

function fillQuestion(nextQuestion: Question) {
  question.value = nextQuestion;
  if (!nextQuestion.parse_warnings?.includes('ai_readability_needs_review')) {
    readabilityReview.value = null;
  }
  Object.keys(form).forEach((key) => delete form[key]);
  Object.assign(form, {
    ...nextQuestion,
    option_a: nextQuestion.option_a || '',
    option_b: nextQuestion.option_b || '',
    option_c: nextQuestion.option_c || '',
    option_d: nextQuestion.option_d || '',
    answer: nextQuestion.answer || '',
    analysis: nextQuestion.analysis || '',
    needs_review: nextQuestion.needs_review,
    status: nextQuestion.status,
  });
  dirty.value = false;
}

function buildPayload(status?: 'draft' | 'published') {
  return {
    content: form.content,
    option_a: form.option_a,
    option_b: form.option_b,
    option_c: form.option_c,
    option_d: form.option_d,
    answer: form.answer,
    analysis: form.analysis,
    status: status || form.status,
    needs_review: status === 'published' ? false : form.needs_review,
  };
}

function handleRegionSelected(region: RegionSelection) {
  selectedRegion.value = region;
  actionDialogVisible.value = true;
}

function prepareImageReplacement(target: ImageTarget, index: number) {
  pendingImageReplacement.value = { target, index };
  regionMode.value = true;
  ElMessage.info('请在右侧 PDF 框选新的图片区域');
}

async function runRegionOcr(mode: OcrRegionMode) {
  if (!selectedRegion.value || !question.value) return;
  activeOcrMode.value = mode;
  ocrLoading.value = true;
  try {
    const result = await ocrPdfRegion({
      task_id: question.value.pdf_source?.task_id || question.value.parse_task_id,
      file_url: question.value.pdf_source?.file_url,
      page_num: selectedRegion.value.page_num,
      bbox: selectedRegion.value.bbox,
      mode,
      question_id: question.value.id,
    });
    ocrResult.value = result;
    ocrText.value = result.text || '';
    for (const key of optionKeys) {
      ocrOptions[key] = result.options?.[key as 'A' | 'B' | 'C' | 'D'] || '';
    }
    actionDialogVisible.value = false;
    ocrDialogVisible.value = true;
  } finally {
    ocrLoading.value = false;
  }
}

async function saveRegionImage(target: 'question' | 'material') {
  if (!selectedRegion.value || !question.value) return;
  ocrLoading.value = true;
  try {
    const result = await ocrPdfRegion({
      task_id: question.value.pdf_source?.task_id || question.value.parse_task_id,
      file_url: question.value.pdf_source?.file_url,
      page_num: selectedRegion.value.page_num,
      bbox: selectedRegion.value.bbox,
      mode: 'image',
      question_id: question.value.id,
    });
    if (!result.image_url) {
      ElMessage.warning('截图保存失败，未返回图片地址');
      return;
    }
    const image = manualImagePayload(result, target);
    if (target === 'material') {
      await appendMaterialImage(image);
    } else {
      await appendQuestionImage(image);
    }
    actionDialogVisible.value = false;
    ElMessage.success(target === 'material' ? '已保存为材料图片' : '已保存为题目图片');
  } finally {
    ocrLoading.value = false;
  }
}

async function replaceSelectedImage() {
  if (!pendingImageReplacement.value || !selectedRegion.value || !question.value) return;
  const { target, index } = pendingImageReplacement.value;
  ocrLoading.value = true;
  try {
    const result = await ocrPdfRegion({
      task_id: question.value.pdf_source?.task_id || question.value.parse_task_id,
      file_url: question.value.pdf_source?.file_url,
      page_num: selectedRegion.value.page_num,
      bbox: selectedRegion.value.bbox,
      mode: 'image',
      question_id: question.value.id,
    });
    if (!result.image_url) {
      ElMessage.warning('截图保存失败，未返回图片地址');
      return;
    }
    const image = manualImagePayload(result, target);
    if (target === 'material') {
      await replaceMaterialImage(index, image);
    } else {
      await replaceQuestionImage(index, image);
    }
    pendingImageReplacement.value = null;
    actionDialogVisible.value = false;
    ElMessage.success('已用框选区域替换图片');
  } finally {
    ocrLoading.value = false;
  }
}

async function applyOcr(mode: 'replace' | 'append') {
  if (!question.value || !ocrResult.value) return;
  applyingOcr.value = true;
  try {
    if (activeOcrMode.value === 'options') {
      const previous = pickQuestionFields(['option_a', 'option_b', 'option_c', 'option_d']);
      const payload = {
        option_a: ocrOptions.A || form.option_a || '',
        option_b: ocrOptions.B || form.option_b || '',
        option_c: ocrOptions.C || form.option_c || '',
        option_d: ocrOptions.D || form.option_d || '',
      };
      await updateQuestion(questionId, payload);
      lastUndo.value = {
        label: '撤销选项修复',
        apply: async () => {
          await updateQuestion(questionId, previous);
          fillQuestion(await getQuestion(questionId));
        },
      };
    } else if (activeOcrMode.value === 'material') {
      await applyMaterialText(mode);
    } else {
      const field = activeOcrMode.value === 'analysis' ? 'analysis' : 'content';
      const previous = pickQuestionFields([field]);
      const current = String(form[field] || '');
      const nextValue = mode === 'append' ? joinText(current, ocrText.value) : ocrText.value;
      await updateQuestion(questionId, { [field]: nextValue });
      lastUndo.value = {
        label: `撤销${activeOcrMode.value === 'analysis' ? '解析' : '题干'}修复`,
        apply: async () => {
          await updateQuestion(questionId, previous);
          fillQuestion(await getQuestion(questionId));
        },
      };
    }
    fillQuestion(await getQuestion(questionId));
    ocrDialogVisible.value = false;
    ElMessage.success('已写入当前题');
  } finally {
    applyingOcr.value = false;
  }
}

async function applyMaterialText(mode: 'replace' | 'append') {
  const material = question.value?.material;
  if (!material?.id) {
    ElMessage.warning('当前题没有关联材料，无法写入材料');
    return;
  }
  const previous = { content: material.content || '' };
  const nextContent = mode === 'append' ? joinText(material.content || '', ocrText.value) : ocrText.value;
  await updateMaterial(material.id, { content: nextContent });
  lastUndo.value = {
    label: '撤销材料修复',
    apply: async () => {
      await updateMaterial(material.id, previous);
      fillQuestion(await getQuestion(questionId));
    },
  };
}

async function appendQuestionImage(image: Record<string, unknown>) {
  const oldImages = [...(question.value?.images || [])];
  const nextImages = [...oldImages, image];
  await updateQuestion(questionId, { images: nextImages });
  lastUndo.value = {
    label: '撤销题目图片',
    apply: async () => {
      await updateQuestion(questionId, { images: oldImages });
      fillQuestion(await getQuestion(questionId));
    },
  };
  fillQuestion(await getQuestion(questionId));
}

async function replaceQuestionImage(index: number, image: Record<string, unknown>) {
  const oldImages = [...(question.value?.images || [])];
  if (index < 0 || index >= oldImages.length) {
    ElMessage.warning('要替换的题目图片不存在');
    return;
  }
  const nextImages = oldImages.map((item, itemIndex) => (itemIndex === index ? image : item));
  await updateQuestion(questionId, { images: nextImages });
  lastUndo.value = {
    label: '撤销题目图片替换',
    apply: async () => {
      await updateQuestion(questionId, { images: oldImages });
      fillQuestion(await getQuestion(questionId));
    },
  };
  fillQuestion(await getQuestion(questionId));
}

async function appendMaterialImage(image: Record<string, unknown>) {
  const material = question.value?.material;
  if (!material?.id) {
    ElMessage.warning('当前题没有关联材料，无法保存为材料图片');
    return;
  }
  const oldImages = [...(material.images || [])];
  const nextImages = [...oldImages, image];
  await updateMaterial(material.id, { images: nextImages });
  lastUndo.value = {
    label: '撤销材料图片',
    apply: async () => {
      await updateMaterial(material.id, { images: oldImages });
      fillQuestion(await getQuestion(questionId));
    },
  };
  fillQuestion(await getQuestion(questionId));
}

async function replaceMaterialImage(index: number, image: Record<string, unknown>) {
  const material = question.value?.material;
  if (!material?.id) {
    ElMessage.warning('当前题没有关联材料，无法替换材料图片');
    return;
  }
  const oldImages = [...(material.images || [])];
  if (index < 0 || index >= oldImages.length) {
    ElMessage.warning('要替换的材料图片不存在');
    return;
  }
  const nextImages = oldImages.map((item, itemIndex) => (itemIndex === index ? image : item));
  await updateMaterial(material.id, { images: nextImages });
  lastUndo.value = {
    label: '撤销材料图片替换',
    apply: async () => {
      await updateMaterial(material.id, { images: oldImages });
      fillQuestion(await getQuestion(questionId));
    },
  };
  fillQuestion(await getQuestion(questionId));
}

async function deleteImage(target: ImageTarget, index: number) {
  try {
    await ElMessageBox.confirm('删除后可通过“撤销最近修复”恢复。', '删除图片', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    });
  } catch {
    return;
  }
  if (target === 'material') {
    await deleteMaterialImage(index);
  } else {
    await deleteQuestionImage(index);
  }
}

async function deleteQuestionImage(index: number) {
  const oldImages = [...(question.value?.images || [])];
  if (index < 0 || index >= oldImages.length) return;
  const nextImages = oldImages.filter((_, itemIndex) => itemIndex !== index);
  await updateQuestion(questionId, { images: nextImages });
  lastUndo.value = {
    label: '撤销删除题目图片',
    apply: async () => {
      await updateQuestion(questionId, { images: oldImages });
      fillQuestion(await getQuestion(questionId));
    },
  };
  fillQuestion(await getQuestion(questionId));
  ElMessage.success('已删除题目图片');
}

async function deleteMaterialImage(index: number) {
  const material = question.value?.material;
  if (!material?.id) return;
  const oldImages = [...(material.images || [])];
  if (index < 0 || index >= oldImages.length) return;
  const nextImages = oldImages.filter((_, itemIndex) => itemIndex !== index);
  await updateMaterial(material.id, { images: nextImages });
  lastUndo.value = {
    label: '撤销删除材料图片',
    apply: async () => {
      await updateMaterial(material.id, { images: oldImages });
      fillQuestion(await getQuestion(questionId));
    },
  };
  fillQuestion(await getQuestion(questionId));
  ElMessage.success('已删除材料图片');
}

async function handleUndo() {
  if (!lastUndo.value) return;
  const undo = lastUndo.value;
  await undo.apply();
  lastUndo.value = null;
  ElMessage.success(undo.label);
}

function manualImagePayload(result: OcrRegionResult, target: 'question' | 'material') {
  return {
    ref: `manual-q${questionId}-p${result.page_num}-${Date.now()}`,
    url: result.image_url,
    caption: '',
    page: result.page_num,
    role: target === 'material' ? 'manual_material_region' : 'manual_region',
    bbox: result.bbox,
    source: 'manual_crop',
  };
}

function pickQuestionFields(keys: string[]) {
  return Object.fromEntries(keys.map((key) => [key, form[key] ?? '']));
}

function joinText(current: string, addition: string) {
  return [current.trim(), addition.trim()].filter(Boolean).join('\n\n');
}

async function handleSave() {
  saving.value = true;
  try {
    await updateQuestion(questionId, buildPayload());
    fillQuestion(await getQuestion(questionId));
    ElMessage.success('已保存');
  } finally {
    saving.value = false;
  }
}

async function handlePublish() {
  publishing.value = true;
  try {
    await updateQuestion(questionId, buildPayload('published'));
    fillQuestion(await getQuestion(questionId));
    ElMessage.success('已保存并通过');
  } finally {
    publishing.value = false;
  }
}

async function handleAiReview() {
  if (!question.value) return;
  aiReviewLoading.value = true;
  try {
    readabilityReview.value = await reviewQuestionReadability(questionId);
    fillQuestion(await getQuestion(questionId));
    if (readabilityReview.value.needs_review) {
      ElMessage.warning('AI预审认为该题需要重新框选或复查');
    } else {
      ElMessage.success('AI预审通过，未修改题目内容');
    }
  } finally {
    aiReviewLoading.value = false;
  }
}

function focusAreaText(area: string) {
  return {
    stem: '题干',
    options: '选项',
    material: '材料',
    images: '图片',
    analysis: '解析',
    warnings: '警告',
  }[area] || area;
}

function resetPdfPage() {
  currentPdfPage.value = Math.max(1, Number(sourcePage.value) || 1);
}

function openPdf() {
  if (!pdfViewerSrc.value) return;
  window.open(pdfViewerSrc.value, '_blank', 'noopener,noreferrer');
}

function normalizeImageList(images: NonNullable<Question['images']>): PreviewImage[] {
  return images
    .map((image) => {
      if (typeof image === 'string') return { src: image };
      const base64 = image.base64 ? `data:image/png;base64,${image.base64}` : '';
      return {
        src: image.url || base64,
        ref: image.ref,
        caption: image.caption,
        role: image.role,
        bbox: image.bbox,
        source: image.source,
        assignmentConfidence: image.assignment_confidence,
      };
    })
    .filter((image) => image.src);
}

onMounted(fetchQuestion);
</script>

<style scoped>
.preview-page {
  min-height: 100%;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.preview-layout {
  display: grid;
  grid-template-columns: minmax(420px, 0.92fr) minmax(520px, 1.08fr);
  gap: 16px;
}

.question-surface,
.source-panel {
  min-width: 0;
}

.question-surface,
.pdf-panel,
.info-block {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.question-surface {
  padding: 24px;
}

.question-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e5e7eb;
}

.question-index {
  color: #111827;
  font-size: 22px;
  font-weight: 700;
}

.question-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.preview-section {
  padding: 22px 0;
  border-bottom: 1px solid #edf0f5;
}

.preview-section:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

h2 {
  margin: 0 0 12px;
  color: #374151;
  font-size: 15px;
  font-weight: 650;
}

.stem-text,
.material-text,
.analysis-text {
  margin: 0;
  color: #111827;
  font-size: 16px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.material-text {
  color: #374151;
  font-size: 15px;
}

.option-list {
  display: grid;
  gap: 10px;
}

.option-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fafafa;
  line-height: 1.6;
}

.option-key {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #111827;
  color: #fff;
  font-weight: 700;
}

.answer-section {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 24px;
}

.answer-value {
  font-size: 24px;
  font-weight: 750;
}

.answer-image {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.source-panel {
  display: grid;
  align-content: start;
  gap: 16px;
}

.pdf-panel {
  padding: 16px;
}

.pdf-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.pdf-file {
  max-width: 420px;
  overflow: hidden;
  color: #6b7280;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pdf-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.region-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.region-alert {
  margin-bottom: 12px;
}

.region-actions .el-button {
  margin: 0;
}

.ocr-review {
  display: grid;
  gap: 14px;
}

.ocr-diff {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}

.ocr-diff h3 {
  margin: 0 0 8px;
  color: #374151;
  font-size: 13px;
}

.ocr-diff pre {
  min-height: 180px;
  max-height: 360px;
  padding: 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
}

.ocr-option-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.info-block {
  padding: 16px;
}

dl {
  display: grid;
  gap: 14px;
  margin: 0;
}

dt {
  color: #6b7280;
  font-size: 12px;
}

dd {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0 0;
  color: #111827;
  word-break: break-all;
}

pre {
  max-height: 520px;
  margin: 0;
  overflow: auto;
  color: #374151;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

:deep(.image-gallery) {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 14px;
  margin-top: 14px;
}

:deep(.preview-image-item) {
  min-width: 0;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

:deep(.preview-image-item.pending-replace) {
  border-color: #e6a23c;
  background: #fffbeb;
}

:deep(.image-caption) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  color: #4b5563;
  font-size: 12px;
  line-height: 1.4;
}

:deep(.image-pill) {
  padding: 2px 6px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #047857;
}

:deep(.image-pill.muted) {
  background: #f3f4f6;
  color: #4b5563;
}

:deep(.image-actions) {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

:deep(.image-actions .el-button) {
  margin: 0;
  padding: 0;
}

@media (max-width: 1100px) {
  .preview-layout,
  .answer-section {
    grid-template-columns: 1fr;
  }
}
</style>
