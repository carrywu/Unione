<template>
  <div class="page review-page">
    <PageHeader>
      <template #actions>
        <div class="review-header-actions">
          <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
          <el-button :icon="Iphone" :disabled="!selected" @click="mobilePreviewVisible = true">移动端预览</el-button>
          <el-button type="primary" :icon="List" @click="router.push(`/banks/${bankId}/questions`)">题目列表</el-button>
        </div>
      </template>
    </PageHeader>
    <div class="review-row">
      <section class="review-list-region">
        <div class="panel left-panel">
          <div class="stats">
            <el-statistic title="全部" :value="stats.total" />
            <el-statistic title="已发布" :value="stats.published" />
            <el-statistic title="待审核" :value="stats.needs_review" />
            <el-statistic title="草稿" :value="stats.draft" />
          </div>

          <div class="filters">
            <el-tabs v-model="tab" @tab-change="handleTabChange">
              <el-tab-pane label="全部" name="all" />
              <el-tab-pane label="待审核" name="review" />
              <el-tab-pane label="已发布" name="published" />
            </el-tabs>
            <el-tooltip
              v-if="tab !== 'published'"
              placement="top"
              :disabled="Boolean(batchPublishableCount)"
              :content="batchPublishDisabledReason"
            >
              <span class="batch-button-wrap">
                <el-button
                  type="success"
                  :icon="Check"
                  :loading="batchLoading"
                  :disabled="!batchPublishableCount"
                  @click="handleBatchPublish"
                >
                  批量通过{{ batchPublishableCount ? ` ${batchPublishableCount}` : '' }}
                </el-button>
              </span>
            </el-tooltip>
          </div>

          <el-scrollbar class="question-scroll" v-loading="loading">
            <div v-if="!loading && !questions.length" class="question-empty">
              <strong>当前筛选下没有题目</strong>
              <span>切换上方筛选，或返回题目列表检查题库内容。</span>
            </div>
            <div
              v-for="question in questions"
              :key="question.id"
              class="question-card"
              :class="{ active: selected?.id === question.id, review: question.needs_review }"
              role="button"
              tabindex="0"
              @click="selectQuestion(question)"
              @keydown.enter.prevent="selectQuestion(question)"
              @keydown.space.prevent="selectQuestion(question)"
            >
              <div class="card-head">
                <div class="card-title">
                  <strong>{{ question.index_num }}.</strong>
                  <span class="source-pill">{{ questionSource(question) }}</span>
                </div>
                <div class="card-status">
                  <StatusTag :status="question.status" :needs-review="question.needs_review" />
                  <span class="open-hint">{{ selected?.id === question.id ? '编辑中' : '编辑' }}</span>
                </div>
              </div>
              <div class="card-content">{{ questionBrief(question) }}</div>
              <div class="card-foot">
                <span v-if="question.needs_review" class="review-pill">需复查</span>
                <span v-if="confidenceText(question)" class="meta-chip">{{ confidenceText(question) }}</span>
                <span v-if="pageText(question)" class="meta-chip">{{ pageText(question) }}</span>
                <span v-if="normalizeImages(question).length" class="meta-chip icon-chip">
                  <el-icon><Picture /></el-icon>{{ normalizeImages(question).length }} 图
                </span>
                <span v-if="question.parse_warnings?.length" class="meta-chip warning-chip">
                  {{ warningSummary(question.parse_warnings) }}
                </span>
              </div>
            </div>
          </el-scrollbar>

          <div class="pagination">
            <el-pagination
              v-model:current-page="query.page"
              v-model:page-size="query.pageSize"
              size="small"
              :total="total"
              layout="prev, pager, next"
              @current-change="fetchQuestions"
            />
          </div>
        </div>
      </section>

      <section class="review-editor-region">
        <div class="panel editor-panel">
          <el-empty v-if="!selected" description="暂无可编辑题目。请切换筛选或返回题目列表。" />
          <el-form v-else label-position="top" :model="form" class="question-form">
            <div class="editor-head">
              <div>
                <span class="index">第 {{ form.index_num }} 题</span>
                <el-select v-model="form.type" size="small" class="type-select" @change="dirty = true">
                  <el-option label="单选题" value="single" />
                  <el-option label="判断题" value="judge" />
                </el-select>
              </div>
              <div class="editor-actions">
                <el-button size="small" :icon="Iphone" @click="mobilePreviewVisible = true">
                  移动端预览
                </el-button>
                <el-button size="small" @click="router.push(`/banks/${bankId}/questions/${selected.id}/preview`)">
                  <el-icon><Aim /></el-icon>
                  PDF定位
                </el-button>
                <el-button size="small" :loading="aiRepairLoading" @click="handleAiRepair">
                  AI修复当前题
                </el-button>
                <StatusTag :status="form.status" :needs-review="form.needs_review" />
              </div>
            </div>

            <div v-if="form.page_num || form.page_range || form.source || form.parse_confidence != null || form.parse_warnings?.length" class="parse-meta">
              <div class="meta-row" v-if="form.page_num">
                <span class="meta-label">页码</span>
                <el-tag size="small" type="info">第 {{ form.page_num }} 页</el-tag>
              </div>
              <div class="meta-row" v-if="form.page_range?.length">
                <span class="meta-label">跨页范围</span>
                <el-tag size="small" type="info">{{ form.page_range.join(' - ') }}</el-tag>
              </div>
              <div class="meta-row" v-if="form.source">
                <span class="meta-label">解析策略</span>
                <el-tag size="small">{{ form.source }}</el-tag>
              </div>
              <div class="meta-row" v-if="form.parse_confidence != null">
                <span class="meta-label">置信度</span>
                <el-tag size="small" :type="confidenceType">{{ (form.parse_confidence * 100).toFixed(0) }}%</el-tag>
              </div>
              <div class="meta-row" v-if="form.image_refs?.length">
                <span class="meta-label">图片引用</span>
                <el-tag v-for="ref in form.image_refs" :key="ref" size="small" type="info">{{ ref }}</el-tag>
              </div>
              <div class="meta-row warning-row" v-if="form.parse_warnings?.length">
                <span class="meta-label">解析警告</span>
                <el-tag v-for="warning in form.parse_warnings" :key="warning" size="small" type="danger">{{ warningLabel(warning) }}</el-tag>
              </div>
              <div class="blacklist-row">
                <el-input
                  v-model="blacklistText"
                  size="small"
                  placeholder="输入或粘贴页眉页脚文本"
                  clearable
                />
                <el-button size="small" :loading="blacklistLoading" @click="handleAddBlacklistText">
                  加入黑名单
                </el-button>
              </div>
            </div>
            <el-collapse v-if="form.raw_text" class="raw-text-collapse">
              <el-collapse-item title="原始文本" name="raw">
                <div class="raw-text-content">{{ form.raw_text }}</div>
              </el-collapse-item>
            </el-collapse>

            <el-collapse v-if="selected.material?.content || normalizeMaterialImages(selected).length" class="material-collapse" model-value="material">
              <el-collapse-item title="材料内容 / 材料图片" name="material">
                <div class="material-text">{{ selected.material?.content }}</div>
                <div v-if="normalizeMaterialImages(selected).length" class="image-section material-images">
                  <div v-for="(image, index) in normalizeMaterialImages(selected)" :key="index" class="image-item">
                    <ImagePreview :src="image.src" />
                    <div class="image-meta">
                      <el-tag v-if="image.ref" size="small">{{ image.ref }}</el-tag>
                      <el-tag v-if="image.role" size="small" type="info">{{ image.role }}</el-tag>
                      <span v-if="image.caption">{{ image.caption }}</span>
                    </div>
                  </div>
                </div>
                <el-empty v-else description="该材料暂无图片" :image-size="56" />
              </el-collapse-item>
            </el-collapse>

            <div class="image-review-block">
              <div class="section-title">题目图片 / 图表</div>
              <div v-if="currentImages.length" class="image-section">
                <div v-for="(image, index) in currentImages" :key="image.key" class="image-item">
                  <ImagePreview :src="image.src" />
                  <div class="image-meta">
                    <el-tag v-if="image.ref" size="small">{{ image.ref }}</el-tag>
                    <el-tag v-if="image.role" size="small" type="info">{{ imageRoleLabel(image.role) }}</el-tag>
                    <el-tag v-if="image.insertPosition" size="small" type="info">{{ insertPositionLabel(image.insertPosition) }}</el-tag>
                    <el-tag v-if="image.sameVisualGroupId" size="small" type="success">同组表格</el-tag>
                    <el-tag v-if="image.assignmentConfidence != null" size="small" :type="image.assignmentConfidence >= 0.65 ? 'success' : 'warning'">
                      {{ (image.assignmentConfidence * 100).toFixed(0) }}%
                    </el-tag>
                    <span v-if="image.caption">{{ image.caption }}</span>
                  </div>
                  <el-select
                    class="image-position-select"
                    size="small"
                    :model-value="image.insertPosition || 'below_stem'"
                    @change="handleImagePositionChange(index, $event)"
                  >
                    <el-option
                      v-for="item in imagePositionOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                  <el-input
                    v-model="imageDescs[index]"
                    type="textarea"
                    autosize
                    placeholder="AI 描述"
                    @input="dirty = true"
                  />
                  <div class="image-actions">
                    <el-button size="small" :disabled="imageBusy || index === 0" @click.stop="handleReorderImage(index, -1)">上移</el-button>
                    <el-button size="small" :disabled="imageBusy || index === currentImages.length - 1" @click.stop="handleReorderImage(index, 1)">下移</el-button>
                    <el-button size="small" :disabled="imageBusy || index === currentImages.length - 1" @click.stop="handleMergeImage(index)">合并下一张</el-button>
                    <el-button size="small" :loading="imageBusy" @click.stop="handleMoveImage(index, 'previous')">移到上一题</el-button>
                    <el-button size="small" :loading="imageBusy" @click.stop="handleMoveImage(index, 'next')">移到下一题</el-button>
                    <el-button size="small" type="danger" :loading="imageBusy" @click.stop="handleDeleteImage(index)">删除</el-button>
                  </div>
                </div>
              </div>
              <el-empty v-else description="该题暂无图片；如果题干需要图表，请重新解析 PDF 或检查解析结果" :image-size="56" />
            </div>

            <el-form-item label="题干">
              <el-input v-model="form.content" type="textarea" autosize @input="dirty = true" />
            </el-form-item>

            <template v-if="form.type !== 'judge'">
              <el-form-item v-for="key in optionKeys" :key="key" :label="`选项 ${key}`">
                <el-input v-model="form[`option_${key.toLowerCase()}`]" @input="dirty = true" />
              </el-form-item>
            </template>

            <el-form-item label="正确答案">
              <el-select v-model="form.answer" class="full" @change="dirty = true">
                <template v-if="form.type === 'judge'">
                  <el-option label="对" value="对" />
                  <el-option label="错" value="错" />
                </template>
                <template v-else>
                  <el-option v-for="key in optionKeys" :key="key" :label="key" :value="key" />
                </template>
              </el-select>
            </el-form-item>

            <el-form-item label="解析">
              <el-input v-model="form.analysis" type="textarea" autosize @input="dirty = true" />
            </el-form-item>

            <div v-if="aiSolverPanel.visible" class="ai-solver-panel" :class="{ conflict: aiSolverPanel.conflict, caution: aiSolverPanel.lowConfidence }">
              <div class="ai-solver-head">
                <strong>AI 候选解析</strong>
                <div>
                  <el-tag v-if="aiSolverPanel.provider" size="small" effect="plain">
                    {{ aiSolverPanel.provider }}
                  </el-tag>
                  <el-tag v-if="aiSolverPanel.model" size="small" type="info" effect="plain">
                    {{ aiSolverPanel.model }}
                  </el-tag>
                  <el-tag v-if="aiSolverPanel.rechecked" size="small" type="warning" effect="plain">
                    已 Pro 复核
                  </el-tag>
                  <el-tag v-if="aiSolverPanel.confidenceText" size="small" :type="aiSolverPanel.lowConfidence ? 'warning' : 'success'" effect="plain">
                    {{ aiSolverPanel.confidenceText }}
                  </el-tag>
                  <el-tag v-if="aiSolverPanel.conflict" size="small" type="danger" effect="plain">
                    与官方答案冲突
                  </el-tag>
                </div>
              </div>
              <el-alert
                v-if="aiSolverPanel.conflict"
                title="AI 候选答案与当前答案不一致，采纳前需要人工复核。"
                type="error"
                :closable="false"
                show-icon
              />
              <el-alert
                v-else-if="aiSolverPanel.lowConfidence"
                title="AI 候选答案置信度低于 70%，建议只作为参考。"
                type="warning"
                :closable="false"
                show-icon
              />
              <div class="ai-compact-summary">
                <div class="answer-box official">
                  <span>当前答案</span>
                  <strong>{{ aiSolverPanel.officialAnswer || '-' }}</strong>
                </div>
                <div class="answer-box candidate">
                  <span>AI 候选答案</span>
                  <strong>{{ aiSolverPanel.answer || '-' }}</strong>
                </div>
                <p v-if="aiSolverPanel.summary" class="ai-summary">{{ aiSolverPanel.summary }}</p>
                <div v-if="aiSolverPanel.riskFlags.length" class="ai-tag-row risk-row">
                  <el-tag v-for="item in aiSolverPanel.riskFlags" :key="item" size="small" type="warning" effect="plain">{{ item }}</el-tag>
                </div>
              </div>
              <div class="ai-solver-grid">
                <span v-if="aiSolverPanel.firstModel">首轮模型</span>
                <p v-if="aiSolverPanel.firstModel">{{ aiSolverPanel.firstModel }}</p>
                <span v-if="aiSolverPanel.finalModel">最终模型</span>
                <p v-if="aiSolverPanel.finalModel">{{ aiSolverPanel.finalModel }}</p>
                <span v-if="aiSolverPanel.recheckReason">复核原因</span>
                <p v-if="aiSolverPanel.recheckReason">{{ aiSolverPanel.recheckReason }}</p>
                <span v-if="aiSolverPanel.knowledgePoints.length">知识点</span>
                <div v-if="aiSolverPanel.knowledgePoints.length" class="ai-tag-row">
                  <el-tag v-for="item in aiSolverPanel.knowledgePoints" :key="item" size="small" effect="plain">{{ item }}</el-tag>
                </div>
              </div>
              <el-collapse v-if="aiSolverPanel.analysis" class="ai-analysis-collapse">
                <el-collapse-item title="查看完整 AI 候选解析" name="analysis">
                  <div class="ai-analysis-text">{{ aiSolverPanel.analysis }}</div>
                </el-collapse-item>
              </el-collapse>
              <div class="ai-accept-actions">
                <el-button size="small" :loading="aiAccepting === 'answer'" :disabled="!aiSolverPanel.answer" @click="handleAcceptAiSuggestion('answer')">
                  接受 AI 答案
                </el-button>
                <el-button size="small" :loading="aiAccepting === 'analysis'" :disabled="!aiSolverPanel.analysis" @click="handleAcceptAiSuggestion('analysis')">
                  接受 AI 解析
                </el-button>
                <el-button size="small" type="primary" :loading="aiAccepting === 'both'" :disabled="!aiSolverPanel.answer && !aiSolverPanel.analysis" @click="handleAcceptAiSuggestion('both')">
                  同时接受答案和解析
                </el-button>
              </div>
            </div>

            <div class="actions">
              <el-button type="danger" :icon="Delete" :loading="deleting" @click="handleDelete">删除</el-button>
              <el-button :icon="Check" type="success" :loading="publishing" @click="handlePublish">通过发布</el-button>
              <el-button :icon="DocumentChecked" type="primary" :loading="saving" @click="handleSave">保存</el-button>
            </div>
          </el-form>
        </div>
      </section>
    </div>

    <el-drawer v-model="mobilePreviewVisible" title="移动端预览" size="min(460px, 100vw)" class="mobile-preview-drawer">
      <div class="preview-toolbar">
        <el-radio-group v-model="mobilePreviewMode" size="small">
          <el-radio-button label="answering">作答态</el-radio-button>
          <el-radio-button label="analysis">解析态</el-radio-button>
        </el-radio-group>
        <span>390 × 844</span>
      </div>

      <div class="phone-shell">
        <div class="phone-status">
          <span>9:41</span>
          <span>智能练习</span>
          <span>30:00</span>
        </div>
        <div class="phone-progress">
          <div />
        </div>
        <div class="phone-screen">
          <section v-if="selected?.material?.content" class="phone-material">
            <div class="phone-section-label">材料阅读</div>
            <p>{{ selected.material.content }}</p>
            <img
              v-for="(image, index) in normalizeMaterialImages(selected)"
              :key="`preview-material-${index}`"
              :src="image.src"
              :alt="image.caption || '材料图片'"
            />
          </section>

          <section class="phone-question">
            <div class="phone-question-meta">
              <span>{{ form.type === 'judge' ? '判断' : '单选' }}</span>
              <span>第 {{ form.index_num || '-' }} 题</span>
            </div>
            <img
              v-for="(image, index) in imagesForPosition('above_stem')"
              :key="`preview-image-above-stem-${index}`"
              :src="image.src"
              :alt="image.caption || '题目图片'"
            />
            <h3>{{ form.content || '暂无题干' }}</h3>
            <img
              v-for="(image, index) in imagesForPosition('below_stem')"
              :key="`preview-image-below-stem-${index}`"
              :src="image.src"
              :alt="image.caption || '题目图片'"
            />
            <img
              v-for="(image, index) in imagesForPosition('above_options')"
              :key="`preview-image-above-options-${index}`"
              :src="image.src"
              :alt="image.caption || '题目图片'"
            />
            <div class="phone-options">
              <button
                v-for="option in mobilePreviewOptions"
                :key="option.value"
                type="button"
                :class="{
                  correct: mobilePreviewMode === 'analysis' && option.value === form.answer,
                }"
              >
                <strong>{{ option.value }}</strong>
                <span>{{ option.label }}</span>
              </button>
            </div>
            <img
              v-for="(image, index) in imagesForPosition('below_options')"
              :key="`preview-image-below-options-${index}`"
              :src="image.src"
              :alt="image.caption || '题目图片'"
            />

            <div v-if="mobilePreviewMode === 'analysis'" class="phone-analysis">
              <div class="phone-section-label">解析详情</div>
              <strong>正确答案：{{ answerPreviewLabel }}</strong>
              <p>{{ form.analysis || '暂无解析' }}</p>
            </div>
          </section>
        </div>
        <div class="phone-bottom-bar">
          <button type="button">答题卡</button>
          <button type="button">笔记</button>
          <button type="button" class="primary">{{ mobilePreviewMode === 'analysis' ? '下一题' : '提交答案' }}</button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { Aim, Check, Delete, DocumentChecked, Iphone, List, Picture, Refresh } from '@element-plus/icons-vue';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  mergeQuestionImages,
  moveQuestionImage,
  reorderQuestionImages,
  batchPublish,
  deleteQuestion,
  deleteQuestionImage,
  getQuestion,
  getQuestions,
  getReviewStats,
  repairQuestionWithAi,
  updateQuestion,
  type Question,
  type ReviewStats,
} from '@/api/question';
import { addHeaderFooterBlacklist } from '@/api/pdf';
import ImagePreview from '@/components/ImagePreview.vue';
import PageHeader from '@/components/PageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';

type TabName = 'all' | 'review' | 'published';

const route = useRoute();
const router = useRouter();
const bankId = String(route.params.id);
const optionKeys = ['A', 'B', 'C', 'D'];
const imagePositionOptions = [
  { label: '题干上方', value: 'above_stem' },
  { label: '题干下方', value: 'below_stem' },
  { label: '选项上方', value: 'above_options' },
  { label: '选项下方', value: 'below_options' },
];
const warningLabelMap: Record<string, string> = {
  low_confidence: '低置信度',
  missing_answer: '缺少答案',
  missing_options: '选项不完整',
  missing_analysis: '缺少解析',
  ambiguous_answer: '答案不明确',
  image_assignment_low_confidence: '图片匹配待确认',
  material_match_low_confidence: '材料匹配待确认',
  ai_answer_conflict: 'AI 候选答案冲突',
  low_ai_answer_confidence: 'AI 候选低置信度',
  ai_solver_failed: 'AI 解题失败',
  page_mismatch: '页码可能偏移',
  truncated_content: '内容疑似截断',
  parse_incomplete: '解析不完整',
  duplicate_question_index: '题号重复',
};
const tab = ref<TabName>('all');
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const deleting = ref(false);
const batchLoading = ref(false);
const imageBusy = ref(false);
const aiRepairLoading = ref(false);
const aiAccepting = ref<'' | 'answer' | 'analysis' | 'both'>('');
const blacklistLoading = ref(false);
const dirty = ref(false);
const blacklistText = ref('');
const mobilePreviewVisible = ref(false);
const mobilePreviewMode = ref<'answering' | 'analysis'>('answering');
const questions = ref<Question[]>([]);
const selected = ref<Question | null>(null);
const imageDescs = ref<string[]>([]);
const total = ref(0);
const stats = reactive<ReviewStats>({
  total: 0,
  published: 0,
  needs_review: 0,
  draft: 0,
});
const query = reactive({
  page: 1,
  pageSize: 20,
});
const form = reactive<Partial<Question> & Record<string, any>>({});

const confidenceType = computed(() => {
  const c = form.parse_confidence;
  if (c == null) return 'info';
  if (c >= 0.8) return 'success';
  if (c >= 0.5) return 'warning';
  return 'danger';
});

const batchPublishableCount = computed(
  () => questions.value.filter((question) => !question.needs_review && question.status !== 'published').length,
);

const batchPublishDisabledReason = computed(() => {
  if (tab.value === 'published') return '';
  if (!questions.value.length) return '当前筛选下没有题目';
  return '仅“无需复查且未发布”的题目可批量通过';
});

const mobilePreviewOptions = computed(() => {
  if (form.type === 'judge') {
    return [
      { value: '对', label: '正确' },
      { value: '错', label: '错误' },
    ];
  }
  return optionKeys
    .map((key) => ({
      value: key,
      label: String(form[`option_${key.toLowerCase()}`] || ''),
    }))
    .filter((option) => option.label.trim());
});

const answerPreviewLabel = computed(() => {
  const answer = String(form.answer || '');
  const option = mobilePreviewOptions.value.find((item) => item.value === answer);
  return option ? `${option.value}. ${option.label}` : answer || '未设置';
});

const currentImages = computed(() => normalizeImageList((form.images || []) as NonNullable<Question['images']>));
const aiSolverPanel = computed(() => {
  const confidence = Number(form.ai_answer_confidence);
  const knowledgePoints = stringArray(form.ai_knowledge_points);
  const riskFlags = stringArray(form.ai_risk_flags);
  const lowConfidence = Number.isFinite(confidence) && confidence < 0.7;
  return {
    visible: Boolean(
      form.ai_candidate_answer
      || form.ai_candidate_analysis
      || form.ai_reasoning_summary
      || form.ai_solver_provider
      || form.ai_solver_rechecked
      || form.ai_answer_conflict,
    ),
    provider: String(form.ai_solver_provider || ''),
    model: String(form.ai_solver_final_model || form.ai_solver_model || ''),
    firstModel: String(form.ai_solver_first_model || ''),
    finalModel: String(form.ai_solver_final_model || form.ai_solver_model || ''),
    rechecked: Boolean(form.ai_solver_rechecked),
    recheckReason: String(form.ai_solver_recheck_reason || ''),
    officialAnswer: String(form.answer || ''),
    answer: String(form.ai_candidate_answer || ''),
    analysis: String(form.ai_candidate_analysis || ''),
    summary: String(form.ai_reasoning_summary || ''),
    confidenceText: Number.isFinite(confidence) ? `置信度 ${Math.round(confidence * 100)}%` : '',
    lowConfidence,
    knowledgePoints,
    riskFlags,
    conflict: Boolean(form.ai_answer_conflict),
  };
});

function imagesForPosition(position: string) {
  return currentImages.value.filter((image) => (image.insertPosition || 'below_stem') === position);
}

const currentParams = computed(() => {
  const params: Record<string, unknown> = {
    bankId,
    page: query.page,
    pageSize: query.pageSize,
  };
  if (tab.value === 'review') params.needsReview = true;
  if (tab.value === 'published') params.status = 'published';
  return params;
});

async function fetchStats() {
  Object.assign(stats, await getReviewStats(bankId));
}

async function fetchQuestions() {
  loading.value = true;
  try {
    const result = await getQuestions(currentParams.value);
    questions.value = result.list;
    total.value = result.total;
    if (selected.value) {
      const fresh = questions.value.find((item) => item.id === selected.value?.id);
      if (fresh) {
        fillForm(fresh);
        return;
      }
    }
    if (questions.value.length) {
      fillForm(questions.value[0]);
    } else {
      selected.value = null;
      Object.keys(form).forEach((key) => delete form[key]);
      imageDescs.value = [];
      dirty.value = false;
    }
  } finally {
    loading.value = false;
  }
}

async function refreshAll() {
  await Promise.all([fetchStats(), fetchQuestions()]);
}

async function handleTabChange() {
  query.page = 1;
  selected.value = null;
  dirty.value = false;
  await fetchQuestions();
}

async function selectQuestion(question: Question) {
  if (dirty.value) {
    await ElMessageBox.confirm('有未保存更改，是否继续？', '切换题目', {
      type: 'warning',
    });
  }
  fillForm(question);
}

function fillForm(question: Question) {
  selected.value = question;
  Object.keys(form).forEach((key) => delete form[key]);
  Object.assign(form, {
    ...question,
    content: cleanQuestionText(question.content),
    option_a: question.option_a || '',
    option_b: question.option_b || '',
    option_c: question.option_c || '',
    option_d: question.option_d || '',
    analysis: question.analysis || '',
    answer: question.answer || '',
    ai_image_desc: question.ai_image_desc || '',
    page_num: question.page_num,
    source: question.source || '',
    raw_text: question.raw_text || '',
    parse_confidence: question.parse_confidence,
    page_range: question.page_range || [],
    image_refs: question.image_refs || [],
    parse_warnings: question.parse_warnings || [],
    images: cloneImages(question.images || []),
  });
  imageDescs.value = normalizeImageList(question.images || []).map((image) => image.aiDesc || '');
  dirty.value = false;
}

function normalizeImages(question: Question | null) {
  const images = question?.images || [];
  return normalizeImageList(images);
}

function normalizeMaterialImages(question: Question | null) {
  const materialImages = question?.material?.images || [];
  return normalizeImageList(materialImages);
}

function normalizeImageList(images: NonNullable<Question['images']>) {
  return images
    .map((image, index) => {
      if (typeof image === 'string') return { key: `${image}-${index}`, src: image, aiDesc: '' };
      const base64 = image.base64 ? `data:image/png;base64,${image.base64}` : '';
      return {
        key: image.url || image.base64 || image.ref || `${index}`,
        src: image.url || base64,
        aiDesc: image.ai_desc || '',
        ref: image.ref || '',
        caption: image.caption || '',
        role: image.image_role || image.role || '',
        insertPosition: image.insert_position || '',
        sameVisualGroupId: image.same_visual_group_id || '',
        assignmentConfidence: image.assignment_confidence,
      };
    })
    .filter((image) => image.src);
}

function warningLabel(warning: string) {
  const key = warning.trim().toLowerCase().replace(/\s+/g, '_');
  return warningLabelMap[key] || warning.replace(/_/g, ' ');
}

function warningSummary(warnings: string[]) {
  const labels = warnings.map(warningLabel);
  return labels.length > 1 ? `${labels[0]} +${labels.length - 1}` : labels[0];
}

function stringArray(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function questionBrief(question: Question) {
  const content = String(question.content || '暂无题干').replace(/\s+/g, ' ').trim();
  return content.length > 92 ? `${content.slice(0, 92)}...` : content;
}

function questionSource(question: Question) {
  return question.pdf_source?.file_name || question.source || '未标注来源';
}

function confidenceText(question: Question) {
  if (question.parse_confidence == null) return '';
  return `置信 ${(question.parse_confidence * 100).toFixed(0)}%`;
}

function pageText(question: Question) {
  if (question.page_num) return `第 ${question.page_num} 页`;
  if (question.page_range?.length) return `${question.page_range.join('-')} 页`;
  return '';
}

function buildPayload(status?: 'draft' | 'published') {
  const images = cloneImages((form.images || []) as Question['images']).map((image, index) => {
    if (typeof image === 'string') return image;
    return {
      ...image,
      ai_desc: imageDescs.value[index] || image.ai_desc || '',
      image_order: index + 1,
    };
  });
  const payload = {
    type: form.type,
    content: cleanQuestionText(form.content),
    option_a: form.option_a,
    option_b: form.option_b,
    option_c: form.option_c,
    option_d: form.option_d,
    answer: form.answer,
    analysis: form.analysis,
    ai_image_desc: imageDescs.value.join('\n'),
    images,
    status: status || form.status,
    needs_review: status === 'published' ? false : form.needs_review,
  };
  return payload;
}

function cloneImages(images: Question['images'] = []) {
  return images.map((image) => (typeof image === 'string' ? image : { ...image }));
}

function cleanQuestionText(value: unknown) {
  return String(value || '')
    .split(/\r?\n/)
    .filter((line) => !['【', '】'].includes(line.trim()))
    .join('\n')
    .trim()
    .replace(/^】+/, '')
    .replace(/【+$/, '')
    .trim();
}

async function handleSave() {
  if (!selected.value) return;
  saving.value = true;
  try {
    await updateQuestion(selected.value.id, buildPayload());
    ElMessage.success('已保存');
    dirty.value = false;
    await refreshSelected();
    await fetchStats();
  } finally {
    saving.value = false;
  }
}

// TODO: persist "ignore AI suggestion" once the backend exposes an audit field for ignored AI recommendations.
async function handleAcceptAiSuggestion(scope: 'answer' | 'analysis' | 'both') {
  if (!selected.value) return;
  const payload: Partial<Question> = {};
  if ((scope === 'answer' || scope === 'both') && aiSolverPanel.value.answer) {
    payload.answer = aiSolverPanel.value.answer;
  }
  if ((scope === 'analysis' || scope === 'both') && aiSolverPanel.value.analysis) {
    payload.analysis = aiSolverPanel.value.analysis;
  }
  if (!Object.keys(payload).length) return;
  const label = scope === 'answer' ? 'AI 答案' : scope === 'analysis' ? 'AI 解析' : 'AI 答案和解析';
  const dirtyNote = dirty.value ? '\n当前表单有未保存修改，采纳成功后会刷新当前题。' : '';
  await ElMessageBox.confirm(`确认用${label}覆盖当前题目的对应字段？${dirtyNote}`, '采纳 AI 建议', {
    type: aiSolverPanel.value.conflict || aiSolverPanel.value.lowConfidence ? 'warning' : 'info',
    confirmButtonText: '确认采纳',
    cancelButtonText: '取消',
  });
  aiAccepting.value = scope;
  try {
    await updateQuestion(selected.value.id, payload);
    ElMessage.success(`已采纳${label}`);
    dirty.value = false;
    await refreshSelected();
    await fetchStats();
  } finally {
    aiAccepting.value = '';
  }
}

async function handlePublish() {
  if (!selected.value) return;
  publishing.value = true;
  try {
    await updateQuestion(selected.value.id, buildPayload('published'));
    ElMessage.success('已发布');
    dirty.value = false;
    await refreshSelected();
    await fetchStats();
  } finally {
    publishing.value = false;
  }
}

async function refreshSelected() {
  if (!selected.value) return;
  const detail = await getQuestion(selected.value.id);
  const index = questions.value.findIndex((question) => question.id === detail.id);
  if (index >= 0) questions.value[index] = detail;
  fillForm(detail);
}

async function handleDeleteImage(index: number) {
  if (!selected.value) return;
  await ElMessageBox.confirm('确认删除该图片？保存后移动端预览会同步刷新。', '删除图片', {
    type: 'warning',
  });
  const images = cloneImages((form.images || []) as Question['images']);
  const image = images[index];
  const imageKey = typeof image === 'string' ? image : image?.url || image?.ref || image?.base64 || '';
  images.splice(index, 1);
  imageBusy.value = true;
  try {
    if (imageKey && imageKey.length < 500) {
      await deleteQuestionImage(selected.value.id, imageKey);
    } else {
      await updateQuestion(selected.value.id, { images });
    }
    ElMessage.success('图片已删除');
    await refreshSelected();
  } finally {
    imageBusy.value = false;
  }
}

async function handleReorderImage(index: number, offset: -1 | 1) {
  if (!selected.value) return;
  const images = cloneImages((form.images || []) as Question['images']);
  const targetIndex = index + offset;
  if (targetIndex < 0 || targetIndex >= images.length) return;
  [images[index], images[targetIndex]] = [images[targetIndex], images[index]];
  const imageUrls = images.map((image) => (typeof image === 'string' ? image : image.url || image.ref || image.base64 || ''));
  imageBusy.value = true;
  try {
    await reorderQuestionImages(selected.value.id, imageUrls);
    ElMessage.success('图片顺序已更新');
    await refreshSelected();
  } finally {
    imageBusy.value = false;
  }
}

async function handleMoveImage(index: number, direction: 'previous' | 'next') {
  if (!selected.value) return;
  const image = ((form.images || []) as NonNullable<Question['images']>)[index];
  const imageUrl = typeof image === 'string' ? image : image?.url || image?.ref || image?.base64 || '';
  if (!imageUrl) {
    ElMessage.warning('该图片缺少可移动标识');
    return;
  }
  imageBusy.value = true;
  try {
    await moveQuestionImage(selected.value.id, { image_url: imageUrl, direction });
    ElMessage.success(direction === 'previous' ? '已移动到上一题' : '已移动到下一题');
    await refreshAll();
  } finally {
    imageBusy.value = false;
  }
}

async function handleMergeImage(index: number) {
  if (!selected.value) return;
  const images = (form.images || []) as NonNullable<Question['images']>;
  const current = images[index];
  const next = images[index + 1];
  const imageUrl = typeof current === 'string' ? current : current?.url || current?.ref || current?.base64 || '';
  const nextImageUrl = typeof next === 'string' ? next : next?.url || next?.ref || next?.base64 || '';
  if (!imageUrl || !nextImageUrl) {
    ElMessage.warning('相邻图片缺少可合并标识');
    return;
  }
  imageBusy.value = true;
  try {
    await mergeQuestionImages(selected.value.id, {
      image_url: imageUrl,
      next_image_url: nextImageUrl,
    });
    ElMessage.success('已标记为同一表格组');
    await refreshSelected();
  } finally {
    imageBusy.value = false;
  }
}

async function handleAddBlacklistText() {
  const selectedText = String(window.getSelection?.()?.toString() || '').trim();
  const text = (blacklistText.value || selectedText).trim();
  if (!text) {
    ElMessage.warning('请先输入或选中页眉页脚文本');
    return;
  }
  blacklistLoading.value = true;
  try {
    await addHeaderFooterBlacklist({ text });
    blacklistText.value = '';
    ElMessage.success('已加入页眉页脚黑名单，后续解析会过滤该文本');
  } finally {
    blacklistLoading.value = false;
  }
}

function handleImagePositionChange(index: number, value: string) {
  const images = (form.images || []) as NonNullable<Question['images']>;
  const image = images[index];
  if (!image || typeof image === 'string') return;
  image.insert_position = value;
  dirty.value = true;
}

function imageRoleLabel(role: string) {
  return {
    material: '材料图',
    question_visual: '题目图',
    option_image: '选项图',
    unknown: '未知',
  }[role] || role;
}

function insertPositionLabel(position: string) {
  return {
    above_stem: '题干上方',
    below_stem: '题干下方',
    above_options: '选项上方',
    below_options: '选项下方',
  }[position] || position;
}

async function handleAiRepair() {
  if (!selected.value) return;
  aiRepairLoading.value = true;
  try {
    const proposal = await repairQuestionWithAi(selected.value.id, {
      warnings: form.parse_warnings || [],
      include_neighbors: true,
    });
    const confidence = Math.round((proposal.confidence || 0) * 100);
    const warningText = proposal.warnings?.length ? `\n警告：${proposal.warnings.join('、')}` : '';
    const removedText = proposal.remove_texts?.length ? `\n建议移除：${proposal.remove_texts.join('、')}` : '';
    await ElMessageBox.confirm(
      `AI 已生成修复建议，置信度 ${confidence}%。${warningText}${removedText}\n\n应用后只写入当前编辑框，请人工确认后再保存。`,
      '应用 AI 修复建议？',
      {
        type: proposal.confidence >= 0.75 ? 'info' : 'warning',
        confirmButtonText: '应用到编辑框',
        cancelButtonText: '不应用',
      },
    );
    if (proposal.content) {
      form.content = cleanQuestionText(proposal.content);
    }
    for (const key of optionKeys) {
      const value = proposal.options?.[key as 'A' | 'B' | 'C' | 'D'];
      if (value) form[`option_${key.toLowerCase()}`] = value;
    }
    form.visual_refs = proposal.visual_refs || form.visual_refs || [];
    form.parse_warnings = [...new Set([...(form.parse_warnings || []), ...(proposal.warnings || [])])];
    if ((proposal.confidence || 0) < 0.85 || proposal.warnings?.length) {
      form.needs_review = true;
    }
    dirty.value = true;
    ElMessage.success('AI 修复建议已写入编辑框，请确认后保存');
  } catch (error) {
    if (String((error as Error)?.message || error).includes('cancel')) {
      ElMessage.info('未应用 AI 修复建议');
      return;
    }
    throw error;
  } finally {
    aiRepairLoading.value = false;
  }
}

async function handleDelete() {
  if (!selected.value) return;
  await ElMessageBox.confirm('确认删除该题目？', '删除题目', { type: 'warning' });
  deleting.value = true;
  try {
    await deleteQuestion(selected.value.id);
    ElMessage.success('已删除');
    selected.value = null;
    dirty.value = false;
    await refreshAll();
  } finally {
    deleting.value = false;
  }
}

async function handleBatchPublish() {
  const ids = questions.value
    .filter((question) => !question.needs_review && question.status !== 'published')
    .map((question) => question.id);
  if (!ids.length) {
    ElMessage.warning('没有可批量发布的题目');
    return;
  }
  await ElMessageBox.confirm('确认批量发布所有无需审核的题目？', '批量通过', {
    type: 'warning',
  });
  batchLoading.value = true;
  try {
    await batchPublish(ids);
    ElMessage.success('已批量发布');
    await refreshAll();
  } finally {
    batchLoading.value = false;
  }
}

onMounted(async () => {
  await refreshAll();
  const questionId = String(route.query.questionId || '');
  if (questionId) {
    const target = questions.value.find((question) => question.id === questionId);
    if (target) {
      fillForm(target);
      return;
    }
    try {
      const detail = await getQuestion(questionId);
      fillForm(detail);
    } catch {
      ElMessage.warning('未能加载指定题目详情');
    }
  }
});
</script>

<style scoped>
.review-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 64px);
  min-height: 0;
  overflow: hidden;
}

.review-row {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(0, 1.5fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.review-list-region,
.review-editor-region {
  min-width: 0;
  min-height: 0;
}

.left-panel,
.editor-panel {
  height: 100%;
  min-height: 0;
  padding: 18px;
}

.left-panel {
  display: flex;
  flex-direction: column;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.stats :deep(.el-statistic) {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface-soft);
}

.stats :deep(.el-statistic__head) {
  color: var(--admin-text-faint);
  font-size: 12px;
}

.stats :deep(.el-statistic__content) {
  color: var(--admin-text);
  font-size: 20px;
  font-weight: 760;
}

.filters {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--admin-border);
}

.batch-button-wrap {
  display: inline-flex;
}

.filters :deep(.el-tabs__header) {
  margin: 0;
}

.question-scroll {
  flex: 1;
  min-height: 0;
}

.question-empty {
  display: grid;
  place-items: center;
  gap: 6px;
  min-height: 180px;
  color: var(--admin-text-muted);
  text-align: center;
}

.question-empty strong {
  color: var(--admin-text);
  font-size: 15px;
}

.question-card {
  position: relative;
  margin-bottom: 10px;
  padding: 13px 14px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
  cursor: pointer;
  transition:
    border-color 180ms ease,
    background-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease;
}

.question-card:hover,
.question-card:focus-visible {
  border-color: oklch(77% 0.08 248);
  box-shadow: 0 12px 28px rgb(21 36 61 / 9%);
  outline: none;
  transform: translateY(-1px);
}

.question-card.review {
  border-color: oklch(86% 0.075 68);
  background: oklch(97.5% 0.032 68);
}

.question-card.active {
  border-color: var(--admin-accent);
  background: var(--admin-accent-soft);
  box-shadow: 0 14px 30px rgb(40 91 160 / 15%);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.card-title,
.card-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.card-title {
  flex: 1;
}

.review-pill {
  padding: 2px 7px;
  border: 1px solid oklch(84% 0.08 68);
  border-radius: 999px;
  color: oklch(45% 0.14 52);
  background: oklch(98% 0.03 72);
  font-size: 12px;
  line-height: 1.2;
}

.source-pill {
  overflow: hidden;
  max-width: 180px;
  color: var(--admin-text-faint);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.open-hint {
  color: var(--admin-text-faint);
  font-size: 12px;
  white-space: nowrap;
}

.question-card.active .open-hint {
  color: var(--admin-accent);
  font-weight: 600;
}

.card-content {
  overflow: hidden;
  color: var(--admin-text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.5;
}

.card-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 22px;
  padding: 2px 7px;
  border: 1px solid var(--admin-border);
  border-radius: 999px;
  background: var(--admin-surface-soft);
  color: var(--admin-text-faint);
  font-size: 12px;
  line-height: 1.2;
}

.warning-chip {
  border-color: oklch(86% 0.075 68);
  background: oklch(98% 0.03 72);
  color: oklch(45% 0.14 52);
}

.pagination {
  flex: none;
  display: flex;
  justify-content: center;
  padding-top: 10px;
}

.editor-panel {
  overflow-y: auto;
  overscroll-behavior: contain;
}

.question-form {
  max-width: 920px;
}

.editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  position: sticky;
  top: -18px;
  z-index: 2;
  margin: -18px -18px 16px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--admin-border);
  background: rgb(252 253 255 / 94%);
  backdrop-filter: blur(10px);
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.index {
  margin-right: 10px;
  font-size: 18px;
  font-weight: 760;
}

.material-collapse {
  margin-bottom: 16px;
}

.image-review-block {
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface-soft);
}

.section-title {
  margin-bottom: 10px;
  color: var(--admin-text);
  font-size: 14px;
  font-weight: 740;
}

.material-text {
  white-space: pre-wrap;
  line-height: 1.7;
}

.parse-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--admin-surface-soft);
  border-radius: 8px;
  border: 1px solid var(--admin-border);
  margin-bottom: 14px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.meta-label {
  font-size: 13px;
  color: var(--admin-text-faint);
}

.raw-text-collapse {
  margin-bottom: 14px;
}

.raw-text-content {
  white-space: pre-wrap;
  line-height: 1.6;
  font-size: 13px;
  color: var(--admin-text-muted);
  background: var(--admin-surface-soft);
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  padding: 10px 14px;
  max-height: 200px;
  overflow-y: auto;
}

.ai-solver-panel {
  display: grid;
  gap: 10px;
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid #c9d7ee;
  border-radius: 8px;
  background: #f6f9ff;
}

.ai-solver-panel.conflict {
  border-color: #fecaca;
  background: #fff7f7;
}

.ai-solver-panel.caution:not(.conflict) {
  border-color: #fed7aa;
  background: #fffaf2;
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
  color: var(--admin-text);
  font-size: 13px;
}

.ai-solver-grid > span {
  color: var(--admin-text-faint);
}

.ai-solver-grid p,
.ai-solver-panel > p {
  margin: 0;
  line-height: 1.65;
  color: var(--admin-text-muted);
  white-space: pre-wrap;
}

.ai-compact-summary {
  display: grid;
  grid-template-columns: 120px 120px minmax(0, 1fr);
  gap: 8px;
  align-items: stretch;
}

.answer-box {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
}

.answer-box span {
  color: var(--admin-text-faint);
  font-size: 12px;
}

.answer-box strong {
  color: var(--admin-text);
  font-size: 18px;
}

.answer-box.candidate {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.ai-summary {
  min-width: 0;
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
  color: var(--admin-text-muted);
  font-size: 13px;
  line-height: 1.55;
}

.risk-row {
  grid-column: 1 / -1;
  justify-content: flex-start;
}

.ai-analysis-collapse {
  border: 0;
}

.ai-analysis-text {
  color: var(--admin-text-muted);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.ai-accept-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.full {
  width: 100%;
}

.image-section {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.image-item {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  align-items: start;
  gap: 12px;
}

.material-images .image-item {
  grid-template-columns: 110px 1fr;
}

.image-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.image-position-select {
  grid-column: 2 / 4;
  width: 160px;
}

.image-item :deep(.el-textarea) {
  grid-column: 2 / 4;
}

.image-actions {
  grid-column: 2 / 4;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-start;
}

.review-tip {
  color: #f56c6c;
  font-size: 12px;
  line-height: 32px;
  white-space: nowrap;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  position: sticky;
  bottom: -18px;
  margin: 0 -18px -18px;
  padding: 14px 18px;
  border-top: 1px solid var(--admin-border);
  background: rgb(252 253 255 / 94%);
  backdrop-filter: blur(10px);
}

.review-header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  color: var(--admin-text-faint);
  font-size: 12px;
}

.phone-shell {
  display: flex;
  flex-direction: column;
  width: min(390px, 100%);
  height: min(844px, calc(100vh - 148px));
  min-height: 620px;
  margin: 0 auto;
  overflow: hidden;
  border: 10px solid oklch(22% 0.02 248);
  border-radius: 34px;
  background: #f7f8fc;
  box-shadow: 0 24px 60px rgb(15 23 42 / 18%);
}

.phone-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px 10px;
  background: #fbfcff;
  color: #121826;
  font-size: 12px;
  font-weight: 700;
}

.phone-progress {
  height: 4px;
  background: #d8dde9;
}

.phone-progress div {
  width: 28%;
  height: 100%;
  background: #1f4ea8;
}

.phone-screen {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 14px 96px;
}

.phone-material,
.phone-question,
.phone-analysis {
  border: 1px solid rgba(115, 118, 134, 0.16);
  border-radius: 14px;
  background: #fbfcff;
  box-shadow: 0 10px 28px rgba(31, 78, 168, 0.05);
}

.phone-material {
  margin-bottom: 12px;
  padding: 14px;
}

.phone-question {
  padding: 16px;
}

.phone-section-label {
  margin-bottom: 10px;
  color: #1f4ea8;
  font-size: 13px;
  font-weight: 750;
}

.phone-material p,
.phone-analysis p {
  margin: 0;
  color: #4e5566;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.phone-question-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.phone-question-meta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 10px;
  border-radius: 999px;
  background: #dfe7ff;
  color: #1f4ea8;
  font-size: 12px;
  font-weight: 650;
}

.phone-question h3 {
  margin: 0 0 16px;
  color: #121826;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.65;
  white-space: pre-wrap;
}

.phone-material img,
.phone-question img {
  display: block;
  width: 100%;
  margin-top: 12px;
  border-radius: 12px;
  border: 1px solid #c3c6d7;
  background: #f1f4fb;
}

.phone-options {
  display: grid;
  gap: 10px;
}

.phone-options button {
  display: grid;
  grid-template-columns: 34px 1fr;
  align-items: start;
  gap: 10px;
  width: 100%;
  padding: 13px;
  border: 1px solid rgba(115, 118, 134, 0.18);
  border-radius: 14px;
  background: #fbfcff;
  color: #121826;
  text-align: left;
}

.phone-options button strong {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 50%;
  background: #e8edf7;
  color: #1f4ea8;
}

.phone-options button span {
  line-height: 1.55;
}

.phone-options button.correct {
  border-color: #238260;
  background: #d8f8e7;
}

.phone-options button.correct strong {
  background: #238260;
  color: #f6fff9;
}

.phone-analysis {
  margin-top: 14px;
  padding: 14px;
}

.phone-analysis strong {
  display: block;
  margin-bottom: 8px;
  color: #176a4b;
  line-height: 1.5;
}

.phone-bottom-bar {
  display: grid;
  grid-template-columns: 76px 64px 1fr;
  gap: 8px;
  padding: 10px 12px 14px;
  border-top: 1px solid #d8dde9;
  background: #fbfcff;
}

.phone-bottom-bar button {
  min-height: 42px;
  border: 1px solid #c3c6d7;
  border-radius: 12px;
  background: #fbfcff;
  color: #1f4ea8;
  font-weight: 700;
}

.phone-bottom-bar button.primary {
  border-color: #1f4ea8;
  background: #1f4ea8;
  color: #f8faff;
}

@media (max-width: 1100px) {
  .review-page {
    height: auto;
    min-height: calc(100vh - 64px);
    overflow: visible;
  }

  .review-row {
    grid-template-columns: 1fr;
    height: auto;
  }

  .review-list-region,
  .review-editor-region {
    height: auto;
  }

  .left-panel,
  .editor-panel {
    height: auto;
  }

  .question-scroll {
    height: auto;
    max-height: 420px;
  }

  .editor-panel {
    overflow: visible;
  }

  .question-form {
    max-width: none;
  }
}

@media (max-width: 720px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .filters,
  .editor-head {
    align-items: stretch;
    flex-direction: column;
  }

  .editor-actions,
  .review-header-actions {
    width: 100%;
  }

  .editor-actions .el-button,
  .review-header-actions .el-button {
    flex: 1;
  }

  .image-item,
  .material-images .image-item {
    grid-template-columns: 1fr;
  }

  .actions {
    flex-wrap: wrap;
  }

  .actions .el-button {
    flex: 1;
  }
}
</style>
