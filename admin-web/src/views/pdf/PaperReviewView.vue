<template>
  <div class="paper-review-page">
    <header class="paper-review-header">
      <div>
        <el-button class="back-button" text :icon="ArrowLeft" @click="router.push('/pdf/tasks')">
          返回任务
        </el-button>
        <h1>制卷核对</h1>
        <p>从解析任务候选题生成试卷草稿，所有失败原因和 debug artifact 保持可见。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadCandidates">刷新</el-button>
        <el-button type="primary" :disabled="!draftQuestions.length" :loading="saving" @click="saveDraft">
          保存草稿
        </el-button>
        <el-button type="success" :disabled="!paperId" @click="openPreview">预览试卷</el-button>
        <el-button type="warning" :disabled="!paperId" :loading="publishingPreview" @click="handlePublishPreview">
          Preview 发布
        </el-button>
      </div>
    </header>

    <section class="overview-band" data-testid="paper-review-overview">
      <div>
        <span>taskId</span>
        <strong>{{ textOr(candidates?.taskId, taskId) }}</strong>
      </div>
      <div>
        <span>bankId</span>
        <strong>{{ textOr(candidates?.bankId, '未读取') }}</strong>
      </div>
      <div>
        <span>paperId</span>
        <strong>{{ textOr(paperId, '未创建') }}</strong>
      </div>
      <div>
        <span>模型</span>
        <strong>{{ textOr(candidates?.provider, 'unknown') }} / {{ textOr(candidates?.model, 'unknown') }}</strong>
      </div>
      <div>
        <span>OCR 主 Provider</span>
        <strong>{{ textOr(candidates?.commercial_ocr?.effective_provider || candidates?.commercial_ocr?.provider_result?.provider_name, '未接入') }}</strong>
      </div>
      <div>
        <span>候选</span>
        <strong>{{ summary.total }} 题</strong>
      </div>
      <div>
        <span>可入卷</span>
        <strong>{{ summary.can_add_count }} 题</strong>
      </div>
      <div>
        <span>需修复</span>
        <strong>{{ summary.need_manual_fix_count }} 题</strong>
      </div>
      <div>
        <span>AI</span>
        <strong>P{{ summary.ai_passed_count }} / W{{ summary.ai_warning_count }} / F{{ summary.ai_failed_count }}</strong>
      </div>
      <div class="debug-path">
        <span>debug</span>
        <strong>{{ textOr(candidates?.debug_dir, '未生成 debug 目录') }}</strong>
      </div>
    </section>

    <el-alert
      v-if="failureMessage"
      class="failure-alert"
      type="warning"
      :closable="false"
      show-icon
      data-testid="paper-review-failure"
      :title="failureMessage"
      :description="failureDescription"
    />
    <el-alert
      v-if="candidates?.non_blocking_warnings?.length"
      class="failure-alert"
      type="info"
      :closable="false"
      show-icon
      title="M5 非阻塞提示"
      :description="candidates?.non_blocking_warnings?.join('；')"
    />

    <main class="review-grid">
      <aside class="candidate-pane" data-testid="candidate-pool">
        <div class="pane-head">
          <div>
            <strong>候选题池</strong>
            <span>{{ filteredCandidates.length }} / {{ candidateRows.length }}</span>
          </div>
          <el-select v-model="filter" size="small">
            <el-option v-for="item in filters" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div v-if="!filteredCandidates.length" class="empty-state">
          <strong>没有可显示候选题</strong>
          <span>{{ failureDescription }}</span>
        </div>
        <button
          v-for="candidate in filteredCandidates"
          :key="candidate.candidate_id"
          type="button"
          class="candidate-row"
          :class="{ active: selectedCandidate?.candidate_id === candidate.candidate_id, blocked: !candidate.can_add_to_paper }"
          @click="selectedCandidateId = candidate.candidate_id"
        >
          <div class="candidate-row-top">
            <strong>{{ questionLabel(candidate) }}</strong>
            <el-tag size="small" :type="auditTagType(candidate.ai_audit_status)" data-testid="candidate-ai-status">
              {{ textOr(candidate.ai_audit_status, 'unknown') }}
            </el-tag>
          </div>
          <p><MathText :text="truncate(textOr(candidate.stem, '题干未能可靠定位'), 72)" fallback="题干未能可靠定位" /></p>
          <div class="candidate-tags" data-testid="candidate-risk-tags">
            <span v-if="candidate.need_manual_fix">need_manual_fix</span>
            <span>{{ candidate.can_add_to_paper ? '可入卷' : '不可自动入卷' }}</span>
            <span v-if="candidate.provider_fallback_used">provider_fallback</span>
            <span v-if="candidate.review_ready === false">review_ready=false</span>
            <span v-if="candidate.extracted_but_incomplete">incomplete</span>
            <span v-if="candidate.manualReviewable === false">无法人工核验</span>
            <span>{{ hasImage(candidate) ? '有图片' : '无图片' }}</span>
            <span v-for="flag in (candidate.risk_flags || []).slice(0, 3)" :key="flag">{{ flag }}</span>
          </div>
          <small v-if="!candidate.can_add_to_paper">{{ candidateMissingContextReason(candidate) }}</small>
        </button>
      </aside>

      <section class="review-pane" data-testid="candidate-selected">
        <div class="pane-head">
          <div>
            <strong>题目核对区</strong>
            <span>{{ selectedCandidate ? questionLabel(selectedCandidate) : '未选择候选题' }}</span>
          </div>
          <div class="candidate-actions" v-if="selectedCandidate">
            <el-button
              type="primary"
              :disabled="!selectedCandidate.can_add_to_paper"
              @click="addToDraft(selectedCandidate, false)"
            >
              加入试卷
            </el-button>
            <el-button
              v-if="selectedCandidate.manualForceAddAllowed"
              type="warning"
              data-testid="manual-force-add-button"
              @click="addToDraft(selectedCandidate, true)"
            >
              人工强制加入
            </el-button>
            <el-tooltip
              v-else-if="selectedCandidate.manualReviewable === false"
              :content="candidateMissingContextReason(selectedCandidate)"
            >
              <el-button type="warning" disabled data-testid="manual-force-add-disabled">
                无法人工核验
              </el-button>
            </el-tooltip>
            <el-button
              size="small"
              type="success"
              data-testid="approve-for-publish-button"
              @click="runReviewAction('approve_for_publish')"
            >
              批准预发布
            </el-button>
            <el-button size="small" type="danger" @click="runReviewAction('quarantine_question')">
              隔离题目
            </el-button>
          </div>
        </div>

        <div v-if="!selectedCandidate" class="empty-state">
          <strong>请选择候选题</strong>
          <span>如果没有候选题，请查看 debug artifact 和模型调用摘要。</span>
        </div>
        <template v-else>
          <article class="question-detail">
            <div class="status-line">
              <el-tag :type="auditTagType(selectedCandidate.ai_audit_status)">
                AI {{ textOr(selectedCandidate.ai_audit_status, 'unknown') }}
              </el-tag>
              <el-tag v-if="selectedCandidate.need_manual_fix" type="warning">need_manual_fix</el-tag>
              <el-tag v-if="selectedCandidate.provider_fallback_used" type="warning" data-testid="provider-fallback-badge">
                provider_fallback
              </el-tag>
              <el-tag v-if="selectedCandidate.review_ready === false" type="danger" data-testid="quality-gate-badge">
                review_ready=false
              </el-tag>
              <el-tag v-if="selectedCandidate.extracted_but_incomplete" type="danger">
                extracted_but_incomplete
              </el-tag>
              <el-tag v-if="selectedCandidate.manualReviewable === false" type="danger" data-testid="not-manually-reviewable-badge">
                无法人工核验
              </el-tag>
              <el-tag :type="selectedCandidate.can_add_to_paper ? 'success' : 'danger'">
                {{ selectedCandidate.can_add_to_paper ? '允许入卷' : '不可自动入卷' }}
              </el-tag>
            </div>
            <div v-if="selectedCandidate.manualReviewable === false" class="not-reviewable-panel">
              <strong data-testid="missing-context-reason">{{ candidateMissingContextReason(selectedCandidate) }}</strong>
              <span data-testid="recommended-rerun-action">{{ candidateRecommendedAction(selectedCandidate) }}</span>
            </div>
            <section>
              <h2>共享材料</h2>
              <div v-if="selectedCandidate.material?.content" class="material-card" data-testid="shared-material-panel">
                <p class="stem-text"><MathText :text="selectedCandidate.material?.content" fallback="材料文本缺失" /></p>
                <div v-if="selectedCandidate.material?.images?.length" class="visual-preview material-preview-grid">
                  <img
                    v-for="(image, imageIndex) in selectedCandidate.material?.images || []"
                    :key="image.asset_id || image.ref || image.url || imageIndex"
                    :src="textOr(image.url || image.image_url || image.src || image.base64, '')"
                    alt="共享材料图表"
                  />
                </div>
              </div>
              <p v-else class="muted">当前候选题未提供共享材料正文。</p>
            </section>
            <section>
              <h2>题干</h2>
              <p class="stem-text" data-testid="selected-question-stem">
                <MathText :text="selectedCandidate.stem" fallback="题干未能可靠定位" />
              </p>
            </section>
            <section>
              <h2>选项</h2>
              <div class="options-grid">
                <div v-for="label in optionLabels" :key="label">
                  <span>{{ label }}</span>
                  <p><MathText :text="selectedCandidate.options?.[label]" fallback="选项缺失" /></p>
                </div>
              </div>
            </section>
            <section>
              <h2>图片 / 图表</h2>
              <div v-if="imagePreviewUrl(selectedCandidate)" class="visual-preview">
                <img :src="imagePreviewUrl(selectedCandidate)" alt="题目图表预览" />
              </div>
              <div v-else class="visual-missing">
                {{ textOr(selectedCandidate.visual_parse_status, '图表预览缺失') }}：{{ textOr(selectedCandidate.cannot_add_reason, '未返回可展示图片，需查看 debug artifact') }}
              </div>
            </section>
            <section data-testid="visual-summary-panel">
              <h2>视觉理解</h2>
              <dl class="evidence-list">
                <div>
                  <dt>visual_parse_status</dt>
                  <dd>{{ textOr(selectedCandidate.visual_parse_status, '未提供') }}</dd>
                </div>
                <div>
                  <dt>visual_summary</dt>
                  <dd><MathText :text="selectedCandidate.visual_summary" fallback="未提供视觉摘要" /></dd>
                </div>
                <div>
                  <dt>visual_confidence</dt>
                  <dd>{{ confidenceText(selectedCandidate.visual_confidence) }}</dd>
                </div>
                <div>
                  <dt>ai_reviewed_before_human</dt>
                  <dd>{{ booleanText(selectedCandidate.ai_reviewed_before_human) }}</dd>
                </div>
                <div>
                  <dt>visual_understanding</dt>
                  <dd>{{ textOr(selectedCandidate.visual_understanding?.visual_grouping_summary, '未触发或未返回') }}</dd>
                </div>
              </dl>
            </section>
            <section data-testid="commercial-ocr-panel">
              <h2>Commercial OCR / Quality Gate</h2>
              <dl class="evidence-list">
                <div>
                  <dt>provider</dt>
                  <dd>{{ providerSummary(selectedCandidate) }}</dd>
                </div>
                <div>
                  <dt>provider_status</dt>
                  <dd>{{ textOr(selectedCandidate.provider_status, '未提供') }}</dd>
                </div>
                <div>
                  <dt>provider_trace_ref</dt>
                  <dd>{{ textOr(selectedCandidate.provider_trace_ref, '未提供') }}</dd>
                </div>
                <div>
                  <dt>grouping_confidence</dt>
                  <dd>{{ confidenceText(selectedCandidate.grouping_confidence) }}</dd>
                </div>
                <div>
                  <dt>review_ready</dt>
                  <dd>{{ qualityBoolText(selectedCandidate.review_ready) }}</dd>
                </div>
                <div>
                  <dt>needs_human_review</dt>
                  <dd>{{ qualityBoolText(selectedCandidate.needs_human_review) }}</dd>
                </div>
                <div>
                  <dt>extracted_but_incomplete</dt>
                  <dd>{{ qualityBoolText(selectedCandidate.extracted_but_incomplete) }}</dd>
                </div>
              </dl>
              <div class="candidate-tags" data-testid="grouping-evidence-list">
                <span v-for="item in (selectedCandidate.grouping_evidence || [])" :key="item">{{ item }}</span>
                <span v-if="!(selectedCandidate.grouping_evidence || []).length">未提供 grouping evidence</span>
              </div>
              <p class="muted" data-testid="quality-gate-summary">
                {{ qualityGateSummaryText(selectedCandidate) }}
              </p>
              <p class="muted" v-if="(selectedCandidate.quality_gate?.blocking_reasons || []).length">
                blocking_reasons：{{ joinList(selectedCandidate.quality_gate?.blocking_reasons) }}
              </p>
              <p class="muted" v-if="(selectedCandidate.validation_warnings || []).length">
                validation_warnings：{{ joinList(selectedCandidate.validation_warnings) }}
              </p>
              <p class="muted" v-if="(selectedCandidate.missing_fields || []).length">
                missing_fields：{{ joinList(selectedCandidate.missing_fields) }}
              </p>
            </section>
            <section class="suggestion-grid">
              <div>
                <h2>答案建议</h2>
                <strong><MathText :text="selectedCandidate.answer_suggestion" fallback="无答案建议" /></strong>
                <p>{{ confidenceText(selectedCandidate.answer_confidence) }}</p>
                <small><MathText :text="selectedCandidate.answer_unknown_reason" fallback="已有答案建议，仍需人工核对" /></small>
              </div>
              <div>
                <h2>解析建议</h2>
                <p><MathText :text="selectedCandidate.analysis_suggestion" fallback="无解析建议" /></p>
                <small><MathText :text="selectedCandidate.analysis_unknown_reason" fallback="已有解析建议，仍需人工核对" /></small>
              </div>
            </section>
            <section>
              <h2>AI 预审核摘要</h2>
              <p><MathText :text="selectedCandidate.ai_audit_summary" fallback="AI 预审核未给出摘要" /></p>
              <p class="muted">结论：{{ textOr(selectedCandidate.ai_audit_verdict, '未给出结论') }}</p>
            </section>
            <section data-testid="risk-flag-list">
              <h2>风险标签</h2>
              <div class="candidate-tags">
                <span v-for="flag in (selectedCandidate.risk_flags || [])" :key="flag">{{ flag }}</span>
                <span v-if="!(selectedCandidate.risk_flags || []).length">无</span>
              </div>
            </section>
            <section>
              <h2>证据关联</h2>
              <dl class="evidence-list" data-testid="source-locator-panel">
                <div>
                  <dt>原卷定位</dt>
                  <dd>{{ sourceLocatorText(selectedCandidate) }}</dd>
                </div>
                <div>
                  <dt>source_page_refs</dt>
                  <dd>{{ joinList(selectedCandidate.source_page_refs) }}</dd>
                </div>
                <div>
                  <dt>source_bbox</dt>
                  <dd>{{ joinList(selectedCandidate.source_bbox) }}</dd>
                </div>
                <div>
                  <dt>source_text_span</dt>
                  <dd>{{ textOr(selectedCandidate.source_text_span, '未提供') }}</dd>
                </div>
                <div>
                  <dt>material_group_id</dt>
                  <dd>{{ textOr(selectedCandidate.material_group_id, '未绑定') }}</dd>
                </div>
                <div>
                  <dt>material_group_question_indexes</dt>
                  <dd>{{ joinList(selectedCandidate.material_group_question_indexes) }}</dd>
                </div>
                <div>
                  <dt>shared_material</dt>
                  <dd>{{ selectedCandidate.shared_material ? 'true' : 'false' }}</dd>
                </div>
                <div>
                  <dt>material_group_reason</dt>
                  <dd>{{ textOr(selectedCandidate.material_group_reason, '未提供') }}</dd>
                </div>
                <div>
                  <dt>page-understanding</dt>
                  <dd>{{ textOr(selectedCandidate.source_artifacts_refs?.page_understanding, '未关联') }}</dd>
                </div>
                <div>
                  <dt>semantic-groups</dt>
                  <dd>{{ textOr(selectedCandidate.source_artifacts_refs?.semantic_groups, '未关联') }}</dd>
                </div>
                <div>
                  <dt>recrop-plan</dt>
                  <dd>{{ textOr(selectedCandidate.source_artifacts_refs?.recrop_plan, '未关联') }}</dd>
                </div>
              </dl>
            </section>
            <section data-testid="image-linkage-list">
              <h2>Image Linkage</h2>
              <div v-if="(selectedCandidate.visual_assets || []).length" class="image-linkage-list">
                <article
                  v-for="(asset, assetIndex) in selectedCandidate.visual_assets || []"
                  :key="asset.asset_id || asset.ref || asset.url || assetIndex"
                  class="image-linkage-card"
                >
                  <strong>{{ textOr(asset.asset_id || asset.ref, `asset-${assetIndex + 1}`) }}</strong>
                  <dl class="evidence-list compact">
                    <div>
                      <dt>page</dt>
                      <dd>{{ textOr(asset.page, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>bbox</dt>
                      <dd>{{ joinList(asset.bbox) }}</dd>
                    </div>
                    <div>
                      <dt>image_role</dt>
                      <dd>{{ textOr(asset.image_role || asset.role, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>belongs_to_question</dt>
                      <dd>{{ booleanText(asset.belongs_to_question) }}</dd>
                    </div>
                    <div>
                      <dt>linked_by</dt>
                      <dd>{{ textOr(asset.linked_by, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>link_reason</dt>
                      <dd>{{ textOr(asset.link_reason, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>visual_hash</dt>
                      <dd>{{ textOr(asset.visual_hash, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>visual_summary</dt>
                      <dd><MathText :text="asset.visual_summary || asset.caption || asset.ai_desc" fallback="未提供" /></dd>
                    </div>
                  </dl>
                </article>
              </div>
              <p v-else class="muted">未返回 image linkage。</p>
            </section>
            <section data-testid="answer-book-panel">
              <h2>M5A 答本 / 解析本对撞</h2>
              <div class="options-grid">
                <div>
                  <span>状态</span>
                  <p>{{ textOr(selectedCandidate.m5_answer_book?.status || selectedCandidate.m5_answer_book?.verdict, candidates?.m5a_verdict || 'blocked') }}</p>
                </div>
                <div>
                  <span>匹配方式</span>
                  <p>{{ textOr(selectedCandidate.m5_answer_book?.match_method, '未提供') }}</p>
                </div>
                <div>
                  <span>匹配置信度</span>
                  <p>{{ confidenceText(selectedCandidate.m5_answer_book?.match_confidence) }}</p>
                </div>
                <div>
                  <span>匹配条目</span>
                  <p>{{ textOr(selectedCandidate.m5_answer_book?.matched_answer_item_id, '未提供') }}</p>
                </div>
                <div>
                  <span>答本答案</span>
                  <p><MathText :text="selectedCandidate.m5_answer_book?.answer_from_answer_book" fallback="未提供答本候选" /></p>
                </div>
                <div>
                  <span>答本解析</span>
                  <p><MathText :text="selectedCandidate.m5_answer_book?.analysis_from_answer_book" fallback="未提供答本候选" /></p>
                </div>
                <div>
                  <span>最终答案建议</span>
                  <p><MathText :text="selectedCandidate.m5_answer_book?.final_answer_suggestion" fallback="未生成最终建议" /></p>
                </div>
                <div>
                  <span>最终解析建议</span>
                  <p><MathText :text="selectedCandidate.m5_answer_book?.final_analysis_suggestion" fallback="未生成最终建议" /></p>
                </div>
              </div>
              <p class="muted">
                {{ textOr(selectedCandidate.m5_answer_book?.empty_state_text, '未提供答本/解析本，暂无答本候选') }}
              </p>
              <p v-if="selectedCandidate.m5_answer_book?.fixture_only" class="muted">
                当前为 seeded fixture，仅用于 UI / 交互验证，不写入正式答案源。
              </p>
              <p v-if="selectedCandidate.m5_answer_book?.conflict_reason" class="muted">
                冲突原因：{{ selectedCandidate.m5_answer_book?.conflict_reason }}
              </p>
              <p v-if="selectedCandidate.m5_answer_book?.unmatched_reason" class="muted">
                未命中原因：{{ selectedCandidate.m5_answer_book?.unmatched_reason }}
              </p>
              <div v-if="(selectedCandidate.m5_answer_book?.evidence || []).length" class="candidate-tags">
                <span v-for="item in selectedCandidate.m5_answer_book?.evidence || []" :key="item">{{ item }}</span>
              </div>
              <div class="candidate-actions">
                <el-button
                  size="small"
                  :loading="actionLoading"
                  :disabled="!selectedCandidate.m5_answer_book?.answer_from_answer_book && !selectedCandidate.m5_answer_book?.analysis_from_answer_book"
                  data-testid="accept-match-button"
                  @click="runReviewAction('accept_match')"
                >
                  accept_match
                </el-button>
                <el-button
                  size="small"
                  :loading="actionLoading"
                  data-testid="reject-match-button"
                  @click="runReviewAction('reject_match')"
                >
                  reject_match
                </el-button>
              </div>
            </section>
            <section data-testid="similarity-panel">
              <h2>M5B 相似题 / 去重</h2>
              <dl class="evidence-list">
                <div>
                  <dt>duplicate_status</dt>
                  <dd>{{ textOr(selectedCandidate.m5_similarity?.duplicate_status, candidates?.m5b_verdict || '未提供') }}</dd>
                </div>
                <div>
                  <dt>duplicate_cluster_id</dt>
                  <dd>{{ textOr(selectedCandidate.m5_similarity?.duplicate_cluster_id, '未提供') }}</dd>
                </div>
                <div>
                  <dt>canonical_question_id</dt>
                  <dd>{{ textOr(selectedCandidate.m5_similarity?.canonical_question_id, '未提供') }}</dd>
                </div>
                <div>
                  <dt>decision_status</dt>
                  <dd>{{ textOr(selectedCandidate.m5_similarity?.decision_status, 'not_reviewed') }}</dd>
                </div>
                <div>
                  <dt>similarity candidates</dt>
                  <dd>{{ (selectedCandidate.m5_similarity?.similarity_candidates || []).length || 0 }}</dd>
                </div>
                <div>
                  <dt>说明</dt>
                  <dd>{{ textOr(selectedCandidate.m5_similarity?.empty_state_text, '暂无相似题候选') }}</dd>
                </div>
              </dl>
              <div
                v-if="(selectedCandidate.m5_similarity?.similarity_candidates || []).length"
                class="image-linkage-list"
              >
                <article
                  v-for="match in selectedCandidate.m5_similarity?.similarity_candidates || []"
                  :key="`${match.question_id || 'unknown'}-${match.edge_type || 'similar'}`"
                  class="image-linkage-card"
                >
                  <div class="candidate-row-top">
                    <strong>{{ similarityCandidateTitle(match) }}</strong>
                    <div class="candidate-tags">
                      <span>{{ textOr(match.edge_type, 'similar') }}</span>
                      <span>{{ similarityScoreText(match.similarity_score) }}</span>
                      <span v-if="match.exact_signature_match">exact_signature</span>
                    </div>
                  </div>
                  <p>
                    <MathText
                      :text="truncate(textOr(match.content || match.source_text_span, '历史题内容缺失'), 120)"
                      fallback="历史题内容缺失"
                    />
                  </p>
                  <dl class="evidence-list compact">
                    <div>
                      <dt>question_id</dt>
                      <dd>{{ textOr(match.question_id, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>bank_id</dt>
                      <dd>{{ textOr(match.bank_id, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>parse_task_id</dt>
                      <dd>{{ textOr(match.parse_task_id, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>source_pages</dt>
                      <dd>{{ similaritySourcePagesText(match.source_page_refs) }}</dd>
                    </div>
                    <div>
                      <dt>status</dt>
                      <dd>{{ textOr(match.status, '未提供') }} / {{ textOr(match.review_status, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>visual_summary</dt>
                      <dd><MathText :text="match.visual_summary" fallback="未提供" /></dd>
                    </div>
                  </dl>
                </article>
              </div>
              <div class="candidate-actions">
                <el-button size="small" :loading="actionLoading" data-testid="keep-both-button" @click="runReviewAction('keep_both')">
                  keep_both
                </el-button>
                <el-button size="small" :loading="actionLoading" @click="runReviewAction('mark_sibling')">
                  mark_sibling
                </el-button>
                <el-button size="small" :loading="actionLoading" data-testid="ignore-similarity-button" @click="runReviewAction('ignore_similarity')">
                  ignore_similarity
                </el-button>
                <el-button size="small" :loading="actionLoading" @click="runReviewAction('mark_duplicate')">
                  mark_duplicate
                </el-button>
              </div>
            </section>
            <section data-testid="manual-action-panel">
              <h2>人工动作</h2>
              <div class="manual-action-grid">
                <el-input
                  v-model="actionReason"
                  type="textarea"
                  autosize
                  placeholder="填写人工决策原因 / 证据摘要"
                />
                <div class="manual-action-row">
                  <el-input v-model="answerOverrideDraft" placeholder="override_answer，例如 A" />
                  <el-button :loading="actionLoading" @click="handleOverrideAnswer">override_answer</el-button>
                </div>
                <div class="manual-action-row">
                  <el-input
                    v-model="analysisOverrideDraft"
                    type="textarea"
                    autosize
                    placeholder="override_analysis，填写人工确认后的解析"
                  />
                  <el-button :loading="actionLoading" @click="handleOverrideAnalysis">override_analysis</el-button>
                </div>
              </div>
            </section>
            <section data-testid="audit-log-panel">
              <h2>Audit Log</h2>
              <div v-if="candidateAuditEvents.length" class="audit-log-list">
                <article
                  v-for="event in candidateAuditEvents"
                  :key="event.id || `${event.action}-${event.created_at}`"
                  class="image-linkage-card"
                >
                  <strong>{{ textOr(event.action, 'unknown_action') }}</strong>
                  <dl class="evidence-list compact">
                    <div>
                      <dt>actor</dt>
                      <dd>{{ textOr(event.actor, 'unknown') }}</dd>
                    </div>
                    <div>
                      <dt>reason</dt>
                      <dd>{{ textOr(event.reason, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>created_at</dt>
                      <dd>{{ textOr(event.created_at, '未提供') }}</dd>
                    </div>
                    <div>
                      <dt>evidence_ids</dt>
                      <dd>{{ joinList(event.evidence_ids) }}</dd>
                    </div>
                  </dl>
                </article>
              </div>
              <p v-else class="muted">暂无人工动作审计事件。</p>
            </section>
          </article>
        </template>
      </section>

      <aside class="draft-pane" data-testid="draft-paper">
        <div class="pane-head">
          <div>
            <strong>试卷草稿</strong>
            <span>{{ draftQuestions.length }} 题 · {{ totalScore }} 分</span>
          </div>
        </div>
        <el-input v-model="paperTitle" class="paper-title-input" />
        <div class="section-editor">
          <span>栏目</span>
          <el-input v-model="sections[0].title" size="small" />
        </div>
        <div v-if="!draftQuestions.length" class="empty-state">
          <strong>尚未加入题目</strong>
          <span>只有 source/material 可核验的 warning 题才允许人工强制加入；无法核验来源的题需要补页或完整 PDF 重跑。</span>
        </div>
        <div v-for="(item, index) in draftQuestions" :key="item.candidate_id" class="draft-question">
          <div>
            <strong>{{ index + 1 }}. {{ questionLabel(item) }}</strong>
            <small><MathText :text="truncate(textOr(item.stem, '题干来源缺失'), 52)" fallback="题干来源缺失" /></small>
          </div>
          <el-input-number v-model="item.score" :min="0" :step="0.5" size="small" />
          <div class="draft-actions">
            <el-button size="small" :disabled="index === 0" @click="moveDraft(index, -1)">上移</el-button>
            <el-button size="small" :disabled="index === draftQuestions.length - 1" @click="moveDraft(index, 1)">下移</el-button>
            <el-button size="small" type="danger" @click="removeDraft(index)">移除</el-button>
          </div>
        </div>
      </aside>
    </main>

    <section class="checklist-band" data-testid="risk-checklist">
      <div class="pane-head">
        <div>
          <strong>核对清单</strong>
          <span>{{ selectedCandidate ? questionLabel(selectedCandidate) : '请选择候选题' }}</span>
        </div>
      </div>
      <div class="checklist-grid">
        <div v-for="item in checklist" :key="item.label" :class="{ failed: !item.ok }">
          <span>{{ item.ok ? '通过' : '需处理' }}</span>
          <strong>{{ item.label }}</strong>
          <p>{{ item.detail }}</p>
        </div>
      </div>
    </section>

    <section v-if="previewPublishMeta" class="checklist-band" data-testid="preview-publish-panel">
      <div class="pane-head">
        <div>
          <strong>Preview 发布</strong>
          <span>preview-only / dry-run，不写入正式题库</span>
        </div>
      </div>
      <dl class="evidence-list">
        <div>
          <dt>publish_status</dt>
          <dd>{{ textOr(previewPublishMeta.publish_status, '未发布') }}</dd>
        </div>
        <div>
          <dt>preview_route</dt>
          <dd>{{ textOr(previewPublishMeta.preview_route, '未提供') }}</dd>
        </div>
        <div>
          <dt>preview_api_path</dt>
          <dd>{{ textOr(previewPublishMeta.preview_api_path, '未提供') }}</dd>
        </div>
        <div>
          <dt>question_count</dt>
          <dd>{{ textOr(previewPublishMeta.question_count, 0) }}</dd>
        </div>
      </dl>
    </section>

    <el-drawer v-model="previewVisible" title="试卷预览" size="720px" data-testid="paper-preview">
      <div v-if="paperPreview" class="paper-preview">
        <h2>{{ textOr(paperPreview.title, paperTitle) }}</h2>
        <p>总分 {{ textOr(paperPreview.score, totalScore) }} · {{ paperPreview.questions?.length || 0 }} 题</p>
        <article v-for="(item, index) in paperPreview.questions || []" :key="item.candidate_id" class="preview-question">
          <h3>
            <span>{{ index + 1 }}. </span>
            <MathText :text="item.stem" fallback="题干来源缺失" />
            <span>（{{ textOr(item.score, 0) }} 分）</span>
          </h3>
          <p v-for="label in optionLabels" :key="label">
            <span>{{ label }}. </span><MathText :text="item.options?.[label]" fallback="选项缺失" />
          </p>
          <strong>答案建议：<MathText :text="item.answer_suggestion" fallback="无" /></strong>
          <p>解析建议：<MathText :text="item.analysis_suggestion" fallback="无" /></p>
        </article>
      </div>
      <div v-else class="empty-state">
        <strong>预览尚未生成</strong>
        <span>请先保存草稿。</span>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Refresh } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import MathText from '@/components/MathText.vue';
import { mathTextToString } from '@/utils/mathText';
import {
  applyPaperReviewAction,
  createDraftPaper,
  getDraftPaper,
  getDraftPaperPreview,
  getPaperCandidates,
  publishDraftPaperPreview,
  updateDraftPaper,
  type DraftPaper,
  type PaperCandidate,
  type PaperCandidatesResponse,
} from '@/api/pdf';

const route = useRoute();
const router = useRouter();
const taskId = computed(() => String(route.params.taskId || ''));
const loading = ref(false);
const saving = ref(false);
const errorMessage = ref('');
const candidates = ref<PaperCandidatesResponse | null>(null);
const selectedCandidateId = ref('');
const filter = ref('all');
const paperId = ref(String(route.query.paperId || ''));
const paperTitle = ref('PDF 解析制卷草稿');
const sections = reactive([{ id: 'section-1', title: '自动候选题', order: 1 }]);
const draftQuestions = ref<Array<PaperCandidate & { score: number; section_id: string; order: number }>>([]);
const previewVisible = ref(false);
const paperPreview = ref<DraftPaper | null>(null);
const actionLoading = ref(false);
const publishingPreview = ref(false);
const actionReason = ref('');
const answerOverrideDraft = ref('');
const analysisOverrideDraft = ref('');
const previewPublishMeta = ref<Record<string, any> | null>(null);
const optionLabels = ['A', 'B', 'C', 'D'] as const;

const filters = [
  { value: 'all', label: '全部' },
  { value: 'addable', label: '可入卷' },
  { value: 'manual', label: '需人工修复' },
  { value: 'failed', label: 'AI failed' },
  { value: 'visual', label: '图表题' },
  { value: 'noAnswer', label: '无答案建议' },
  { value: 'noAnalysis', label: '无解析建议' },
];

const summary = computed(() => candidates.value?.summary || {
  total: 0,
  can_add_count: 0,
  need_manual_fix_count: 0,
  ai_passed_count: 0,
  ai_warning_count: 0,
  ai_failed_count: 0,
});

const candidateRows = computed(() => candidates.value?.questions || []);
const filteredCandidates = computed(() => {
  const rows = candidateRows.value;
  if (filter.value === 'addable') return rows.filter((item) => item.can_add_to_paper);
  if (filter.value === 'manual') return rows.filter((item) => item.need_manual_fix);
  if (filter.value === 'failed') return rows.filter((item) => item.ai_audit_status === 'failed');
  if (filter.value === 'visual') return rows.filter((item) => hasImage(item) || hasVisualRisk(item));
  if (filter.value === 'noAnswer') return rows.filter((item) => !item.answer_suggestion);
  if (filter.value === 'noAnalysis') return rows.filter((item) => !item.analysis_suggestion);
  return rows;
});

const selectedCandidate = computed(() =>
  candidateRows.value.find((item) => item.candidate_id === selectedCandidateId.value) || candidateRows.value[0] || null,
);
const candidateAuditEvents = computed(() => {
  const direct = Array.isArray(selectedCandidate.value?.audit_events)
    ? selectedCandidate.value?.audit_events
    : [];
  return [...direct].sort((left, right) =>
    textOr(right?.created_at, '').localeCompare(textOr(left?.created_at, '')),
  );
});

const failureMessage = computed(() => {
  if (errorMessage.value) return errorMessage.value;
  if (!loading.value && candidates.value && !candidateRows.value.length) return '没有可入卷题目';
  return '';
});

const failureDescription = computed(() =>
  textOr(candidates.value?.debug_dir, '请先确认解析任务完成，并查看 debug artifact、provider 错误和 need_manual_fix 原因。'),
);

const totalScore = computed(() => draftQuestions.value.reduce((sum, item) => sum + Number(item.score || 0), 0));

const checklist = computed(() => {
  const item = selectedCandidate.value;
  if (!item) {
    return [
      { label: '题干完整', ok: false, detail: '未选择候选题' },
      { label: '选项完整', ok: false, detail: '未选择候选题' },
      { label: '图片完整', ok: false, detail: '未选择候选题' },
      { label: 'AI 预审核状态明确', ok: false, detail: '未选择候选题' },
    ];
  }
  const missingOptions = optionLabels.filter((label) => !textOr(item.options?.[label], ''));
  return [
    { label: '题干完整', ok: Boolean(textOr(item.stem, '')), detail: textOr(item.stem, '题干缺失') },
    { label: '选项完整', ok: missingOptions.length === 0, detail: missingOptions.length ? `缺失 ${missingOptions.join(',')}` : 'A/B/C/D 已识别' },
    { label: '图片完整', ok: hasImage(item) || !hasVisualRisk(item), detail: hasImage(item) ? '有图片或图表预览' : '无图片，若为图表题需人工修复' },
    { label: '图表标题完整', ok: !(item.risk_flags || []).includes('chart_title_missing_or_unlocalized'), detail: joinList(item.risk_flags) },
    { label: '答案建议存在或说明原因', ok: Boolean(item.answer_suggestion || item.answer_unknown_reason), detail: textOr(item.answer_suggestion || item.answer_unknown_reason, '无答案建议原因') },
    { label: '解析建议存在或说明原因', ok: Boolean(item.analysis_suggestion || item.analysis_unknown_reason), detail: textOr(item.analysis_suggestion || item.analysis_unknown_reason, '无解析建议原因') },
    { label: 'AI 预审核状态明确', ok: Boolean(item.ai_audit_status), detail: textOr(item.ai_audit_status, 'unknown') },
    { label: '人工核验状态明确', ok: item.manualReviewable !== undefined || Boolean(item.manual_review_status), detail: manualReviewStatusText(item) },
    { label: 'Commercial OCR review_ready', ok: item.review_ready !== false, detail: qualityGateSummaryText(item) },
    { label: '17-20 共享材料关系', ok: !item.shared_material || Boolean(item.material?.content), detail: item.shared_material ? textOr(item.material?.content, '共享材料未透传') : 'standalone' },
    { label: '允许入卷 / 原因明确', ok: item.can_add_to_paper || Boolean(item.cannot_add_reason), detail: item.can_add_to_paper ? '允许入卷' : textOr(item.cannot_add_reason, '原因缺失') },
  ];
});

async function loadCandidates() {
  if (!taskId.value) return;
  loading.value = true;
  errorMessage.value = '';
  try {
    candidates.value = await getPaperCandidates(taskId.value);
    paperTitle.value = `解析任务 ${taskId.value} 制卷草稿`;
    previewPublishMeta.value = candidates.value?.publish_preview || null;
    if (!selectedCandidateId.value && candidateRows.value[0]) {
      selectedCandidateId.value = candidateRows.value[0].candidate_id;
    }
    if (paperId.value) await loadDraftPaper();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '制卷候选题读取失败';
  } finally {
    loading.value = false;
  }
}

async function loadDraftPaper() {
  if (!paperId.value) return;
  const draft = await getDraftPaper(paperId.value);
  paperTitle.value = textOr(draft.title, paperTitle.value);
  sections.splice(
    0,
    sections.length,
    ...((draft.sections || [{ id: 'section-1', title: '自动候选题', order: 1 }]) as Array<{
      id: string;
      title: string;
      order: number;
    }>),
  );
  draftQuestions.value = ((draft.questions || []) as Array<PaperCandidate & { score?: number; section_id?: string; order?: number }>)
    .map((question, index) => ({
      ...question,
      score: Number(question.score ?? 1),
      section_id: question.section_id || sections[0]?.id || 'section-1',
      order: Number(question.order ?? index + 1),
    }));
}

function addToDraft(candidate: PaperCandidate, force: boolean) {
  if (!force && !candidate.can_add_to_paper) {
    ElMessage.warning(textOr(candidate.cannot_add_reason, '该题不可自动入卷'));
    return;
  }
  if (force && !candidate.manualForceAddAllowed) {
    ElMessage.warning(candidateMissingContextReason(candidate));
    return;
  }
  if (draftQuestions.value.some((item) => item.candidate_id === candidate.candidate_id)) {
    ElMessage.info('该题已在草稿中');
    return;
  }
  draftQuestions.value.push({
    ...candidate,
    score: 1,
    section_id: sections[0].id,
    order: draftQuestions.value.length + 1,
  });
}

function moveDraft(index: number, offset: number) {
  const nextIndex = index + offset;
  if (nextIndex < 0 || nextIndex >= draftQuestions.value.length) return;
  const rows = [...draftQuestions.value];
  const [item] = rows.splice(index, 1);
  rows.splice(nextIndex, 0, item);
  draftQuestions.value = rows.map((row, rowIndex) => ({ ...row, order: rowIndex + 1 }));
}

function removeDraft(index: number) {
  draftQuestions.value = draftQuestions.value
    .filter((_, rowIndex) => rowIndex !== index)
    .map((row, rowIndex) => ({ ...row, order: rowIndex + 1 }));
}

async function saveDraft() {
  if (!candidates.value) return;
  saving.value = true;
  try {
    const payload = {
      title: paperTitle.value,
      source_task_id: candidates.value.taskId,
      source_bank_id: candidates.value.bankId,
      sections,
      questions: draftQuestions.value,
    };
    const result = paperId.value
      ? await updateDraftPaper(paperId.value, payload)
      : await createDraftPaper(payload);
    paperId.value = result.paper_id;
    paperTitle.value = result.title;
    router.replace({ query: { ...route.query, paperId: result.paper_id } });
    ElMessage.success('试卷草稿已保存');
  } finally {
    saving.value = false;
  }
}

async function openPreview() {
  if (!paperId.value) await saveDraft();
  if (!paperId.value) return;
  paperPreview.value = await getDraftPaperPreview(paperId.value);
  previewVisible.value = true;
}

function resetActionDrafts() {
  answerOverrideDraft.value = '';
  analysisOverrideDraft.value = '';
}

function defaultActionReason(action: string) {
  const label = selectedCandidate.value ? questionLabel(selectedCandidate.value) : '当前候选题';
  return `${label} ${action}`;
}

async function refreshSelectedCandidate() {
  const keepId = selectedCandidate.value?.candidate_id || selectedCandidateId.value;
  await loadCandidates();
  if (keepId) selectedCandidateId.value = keepId;
}

async function runReviewAction(action: string, extra: Record<string, unknown> = {}) {
  if (!taskId.value || !selectedCandidate.value) return;
  actionLoading.value = true;
  try {
    await applyPaperReviewAction(taskId.value, {
      action,
      candidate_id: selectedCandidate.value.candidate_id,
      question_no: selectedCandidate.value.question_no,
      reason: actionReason.value.trim() || defaultActionReason(action),
      evidence_ids: selectedCandidate.value.source_artifacts_refs
        ? Object.values(selectedCandidate.value.source_artifacts_refs)
        : [],
      ...extra,
    });
    await refreshSelectedCandidate();
    actionReason.value = '';
    ElMessage.success(`已记录动作：${action}`);
  } finally {
    actionLoading.value = false;
  }
}

async function handleOverrideAnswer() {
  const answer = answerOverrideDraft.value.trim().toUpperCase();
  if (!answer) {
    ElMessage.warning('请先填写人工确认后的答案');
    return;
  }
  await runReviewAction('override_answer', { answer });
  resetActionDrafts();
}

async function handleOverrideAnalysis() {
  const analysis = analysisOverrideDraft.value.trim();
  if (!analysis) {
    ElMessage.warning('请先填写人工确认后的解析');
    return;
  }
  await runReviewAction('override_analysis', { analysis });
  resetActionDrafts();
}

async function handlePublishPreview() {
  if (!paperId.value) {
    await saveDraft();
  }
  if (!paperId.value) return;
  publishingPreview.value = true;
  try {
    previewPublishMeta.value = await publishDraftPaperPreview(paperId.value, {
      dry_run: true,
      reason: actionReason.value.trim() || 'preview-only publish from admin review',
      evidence_ids: selectedCandidate.value?.source_artifacts_refs
        ? Object.values(selectedCandidate.value.source_artifacts_refs)
        : [],
    });
    await refreshSelectedCandidate();
    ElMessage.success('Preview 发布已生成，可用于 H5 smoke');
  } finally {
    publishingPreview.value = false;
  }
}

function textOr(value: unknown, fallback: string | number) {
  if (typeof value === 'string') return mathTextToString(value, String(fallback));
  if (value === null || value === undefined) return String(fallback);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return String(fallback);
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function questionLabel(candidate: Pick<PaperCandidate, 'question_no'>) {
  return candidate.question_no ? `第 ${candidate.question_no} 题` : '未识别题号';
}

function auditTagType(status?: string) {
  if (status === 'passed') return 'success';
  if (status === 'warning') return 'warning';
  if (status === 'failed') return 'danger';
  return 'info';
}

function manualReviewStatusText(candidate: PaperCandidate) {
  if (candidate.manualReviewable === false) return '无法人工核验';
  if (candidate.manualForceAddAllowed) return '可人工核验后强制加入';
  if (candidate.can_add_to_paper) return '可自动入卷';
  return textOr(candidate.manual_review_status, '人工核验状态未提供');
}

function candidateMissingContextReason(candidate: PaperCandidate) {
  return textOr(
    candidate.missingContextReason || candidate.cannot_add_reason,
    '无法人工核验：缺少原卷定位或 source evidence，需补齐上下文后重新识别',
  );
}

function candidateRecommendedAction(candidate: PaperCandidate) {
  return textOr(candidate.recommendedAction, '补齐上一页重新识别或使用完整 PDF 重新解析');
}

function sourceLocatorText(candidate: PaperCandidate) {
  if (candidate.source_locator_available) return '原卷定位可用';
  return '原卷定位不可用，不能仅凭候选文本人工放行';
}

function hasImage(candidate: PaperCandidate) {
  return Boolean(imagePreviewUrl(candidate) || (candidate.visual_assets || []).length);
}

function hasVisualRisk(candidate: PaperCandidate) {
  return (candidate.risk_flags || []).some((flag) => /chart|table|visual|image|图|表/i.test(flag));
}

function imagePreviewUrl(candidate: PaperCandidate) {
  const direct = textOr(candidate.preview_image_path, '');
  if (isRenderableImageUrl(direct)) return direct;
  const assetUrl = (candidate.visual_assets || [])
    .map((asset) => textOr(asset.url || asset.image_url || asset.src, ''))
    .find(isRenderableImageUrl);
  return assetUrl || '';
}

function isRenderableImageUrl(value: string) {
  return value.startsWith('http://')
    || value.startsWith('https://')
    || value.startsWith('/uploads/')
    || value.startsWith('data:image/');
}

function confidenceText(value?: number | null) {
  return value === null || value === undefined ? '置信度未提供' : `置信度 ${Number(value).toFixed(2)}`;
}

function providerSummary(candidate: PaperCandidate) {
  const provider = textOr(candidate.provider_name, '未提供');
  const latency = candidate.provider_latency_ms === null || candidate.provider_latency_ms === undefined
    ? 'latency 未提供'
    : `${Number(candidate.provider_latency_ms)}ms`;
  return `${provider} / ${latency}`;
}

function qualityBoolText(value: unknown) {
  if (value === true) return 'true';
  if (value === false) return 'false';
  return '未提供';
}

function qualityGateSummaryText(candidate: PaperCandidate) {
  const gate = candidate.quality_gate;
  if (!gate) return '未返回 commercial OCR quality gate';
  const parts = [
    `review_ready=${qualityBoolText(gate.review_ready)}`,
    `ocr_complete=${qualityBoolText(gate.ocr_complete)}`,
    `visual_assets_preserved=${qualityBoolText(gate.visual_assets_preserved)}`,
    `semantic_consistent=${qualityBoolText(gate.semantic_consistent)}`,
  ];
  return parts.join(' / ');
}

function booleanText(value: unknown) {
  if (value === true) return 'true';
  if (value === false) return 'false';
  return '未提供';
}

function joinList(value: unknown) {
  if (!Array.isArray(value) || !value.length) return '无';
  return value.map((item) => textOr(item, '')).filter(Boolean).join('、') || '无';
}

function similarityCandidateTitle(match: Record<string, any>) {
  const bankId = textOr(match.bank_id, 'unknown-bank');
  const questionNo = match.question_no ? `第 ${match.question_no} 题` : textOr(match.question_id, '未知题目');
  return `${bankId} · ${questionNo}`;
}

function similarityScoreText(value?: number | null) {
  return value === null || value === undefined
    ? 'score 未提供'
    : `score ${Number(value).toFixed(2)}`;
}

function similaritySourcePagesText(value: unknown) {
  if (!Array.isArray(value) || !value.length) return '未提供';
  return value.map((item) => textOr(item, '')).filter(Boolean).join(', ') || '未提供';
}

onMounted(loadCandidates);
</script>

<style scoped>
.paper-review-page {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.paper-review-header,
.overview-band,
.review-grid,
.checklist-band {
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
  box-shadow: var(--admin-shadow-sm);
}

.paper-review-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
}

.paper-review-header h1 {
  margin: 8px 0 4px;
  font-size: 24px;
  line-height: 1.2;
}

.paper-review-header p,
.pane-head span,
.empty-state span,
.muted,
.draft-question small,
.candidate-row small {
  color: var(--admin-text-faint);
}

.header-actions,
.candidate-actions,
.draft-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.overview-band {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
}

.overview-band > div {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 12px;
  background: var(--admin-surface);
}

.overview-band span {
  color: var(--admin-text-faint);
  font-size: 12px;
}

.overview-band strong {
  overflow-wrap: anywhere;
}

.debug-path {
  grid-column: span 2;
}

.failure-alert {
  border-radius: 8px;
}

.review-grid {
  display: grid;
  grid-template-columns: 310px minmax(420px, 1fr) 340px;
  min-height: 640px;
  overflow: hidden;
}

.candidate-pane,
.review-pane,
.draft-pane {
  min-width: 0;
  padding: 14px;
}

.candidate-pane,
.review-pane {
  border-right: 1px solid var(--admin-border);
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.pane-head div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.candidate-row {
  display: grid;
  gap: 8px;
  width: 100%;
  margin-bottom: 10px;
  padding: 10px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.candidate-row.active {
  border-color: var(--admin-accent);
  background: var(--admin-accent-soft);
}

.candidate-row.blocked {
  border-color: oklch(90% 0.05 35);
}

.candidate-row p {
  margin: 0;
  line-height: 1.5;
}

.candidate-row-top,
.status-line,
.candidate-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.candidate-row-top {
  justify-content: space-between;
}

.candidate-tags span {
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--admin-surface-soft);
  color: var(--admin-text-muted);
  font-size: 12px;
}

.question-detail {
  display: grid;
  gap: 16px;
}

.not-reviewable-panel {
  display: grid;
  gap: 4px;
  border: 1px solid oklch(82% 0.12 35);
  border-radius: 8px;
  background: oklch(97% 0.025 35);
  padding: 10px;
}

.not-reviewable-panel span {
  color: var(--admin-text-muted);
}

.question-detail h2,
.suggestion-grid h2 {
  margin: 0 0 8px;
  font-size: 14px;
}

.stem-text {
  white-space: pre-wrap;
  line-height: 1.7;
}

.options-grid,
.suggestion-grid,
.checklist-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.options-grid div,
.suggestion-grid > div,
.checklist-grid > div,
.draft-question,
.preview-question,
.empty-state,
.visual-missing {
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface-soft);
  padding: 10px;
}

.options-grid span {
  color: var(--admin-accent);
  font-weight: 700;
}

.visual-preview {
  max-height: 280px;
  overflow: auto;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: #fff;
}

.visual-preview img {
  display: block;
  max-width: 100%;
}

.evidence-list {
  display: grid;
  gap: 8px;
  margin: 0;
}

.evidence-list div {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 10px;
}

.evidence-list dt {
  color: var(--admin-text-faint);
}

.evidence-list dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.evidence-list.compact div {
  grid-template-columns: 120px minmax(0, 1fr);
}

.image-linkage-list {
  display: grid;
  gap: 10px;
}

.image-linkage-card {
  display: grid;
  gap: 8px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface-soft);
  padding: 10px;
}

.manual-action-grid,
.audit-log-list {
  display: grid;
  gap: 10px;
}

.manual-action-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}

.not-reviewable-panel {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  background: oklch(97% 0.025 35);
  border: 1px solid oklch(84% 0.12 35);
}

.paper-title-input,
.section-editor {
  margin-bottom: 12px;
}

.section-editor {
  display: grid;
  gap: 6px;
}

.draft-question {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 96px;
  gap: 8px;
  margin-bottom: 10px;
}

.draft-actions {
  grid-column: 1 / -1;
}

.checklist-band {
  padding: 14px;
}

.checklist-grid > div.failed {
  border-color: oklch(82% 0.12 35);
  background: oklch(97% 0.025 35);
}

.checklist-grid span {
  color: var(--admin-text-faint);
  font-size: 12px;
}

.checklist-grid strong,
.checklist-grid p {
  display: block;
  margin: 4px 0 0;
}

.paper-preview {
  display: grid;
  gap: 12px;
}

.preview-question h3 {
  margin: 0 0 8px;
  font-size: 15px;
  line-height: 1.5;
}

@media (max-width: 1180px) {
  .overview-band {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .review-grid {
    grid-template-columns: 1fr;
  }

  .candidate-pane,
  .review-pane {
    border-right: 0;
    border-bottom: 1px solid var(--admin-border);
  }
}
</style>
