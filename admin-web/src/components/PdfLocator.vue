<template>
  <div class="pdf-locator">
    <div class="pdf-toolbar">
      <div class="toolbar-group">
        <el-button size="small" :disabled="pageValue <= 1 || documentLoading" @click="goPage(pageValue - 1)">
          上一页
        </el-button>
        <div class="page-control">
          <el-input-number
            v-model="pageValue"
            size="small"
            :min="1"
            :max="pageCount || undefined"
            controls-position="right"
            @change="handlePageInput"
          />
          <span>/ {{ pageCount || '-' }}</span>
        </div>
        <el-button
          size="small"
          :disabled="Boolean(pageCount && pageValue >= pageCount) || documentLoading"
          @click="goPage(pageValue + 1)"
        >
          下一页
        </el-button>
      </div>

      <el-divider direction="vertical" />

      <div class="toolbar-group">
        <el-button size="small" :disabled="documentLoading" @click="zoomOut">缩小</el-button>
        <span class="zoom-value">{{ Math.round(scale * 100) }}%</span>
        <el-button size="small" :disabled="documentLoading" @click="zoomIn">放大</el-button>
        <el-button size="small" :disabled="documentLoading" @click="fitWidth">适宽</el-button>
      </div>

      <div class="toolbar-spacer"></div>
      <el-tag v-if="selectionEnabled" size="small" type="warning">框选识别</el-tag>
      <el-button v-if="openSrc || src" size="small" :disabled="documentLoading" @click="openSource">新窗口打开</el-button>
    </div>

    <div ref="viewportRef" class="pdf-viewport" v-loading="documentLoading" @scroll="handleViewportScroll">
      <div v-if="error" class="pdf-error">
        <el-alert :title="error" type="warning" :closable="false" show-icon />
        <el-button v-if="src" type="primary" link @click="openSource">新窗口打开 PDF</el-button>
      </div>

      <div v-else class="page-stack">
        <div
          v-for="page in pageStates"
          :key="page.pageNum"
          :ref="(el) => setPageWrapRef(page.pageNum, el)"
          class="page-shell"
          :class="{ current: page.pageNum === pageValue }"
          :style="{ width: `${page.width}px`, height: `${page.height}px` }"
        >
          <div class="page-number">第 {{ page.pageNum }} 页</div>
          <canvas
            :ref="(el) => setCanvasRef(page.pageNum, el)"
            class="pdf-canvas"
            :style="{ width: `${page.width}px`, height: `${page.height}px` }"
          />
          <div v-if="page.rendering" class="page-loading">加载中...</div>
          <div v-if="page.error" class="page-loading error">{{ page.error }}</div>
          <div
            v-for="(highlight, index) in highlightsForPage(page.pageNum)"
            :key="index"
            class="pdf-highlight"
            :style="highlightStyle(highlight)"
          >
            <span v-if="highlight.label">{{ highlight.label }}</span>
          </div>
          <div v-if="selectionBox?.pageNum === page.pageNum" class="pdf-selection" :style="selectionStyle" />
          <div
            class="selection-layer"
            :class="{ selecting: selectionEnabled }"
            @mousedown="handleSelectionStart(page.pageNum, $event)"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

type Highlight = {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string;
};

type PageState = {
  pageNum: number;
  width: number;
  height: number;
  pdfWidth: number;
  pdfHeight: number;
  rendered: boolean;
  rendering: boolean;
  error: string;
};

type SelectionBox = {
  pageNum: number;
  x: number;
  y: number;
  width: number;
  height: number;
};

const props = defineProps<{
  src: string;
  openSrc?: string;
  page: number;
  headers?: Record<string, string>;
  highlights?: Highlight[];
  selectionEnabled?: boolean;
}>();

const emit = defineEmits<{
  'update:page': [page: number];
  'region-selected': [region: {
    page_num: number;
    bbox: [number, number, number, number];
    viewport_width: number;
    viewport_height: number;
    pdf_width: number;
    pdf_height: number;
    scale: number;
  }];
}>();

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const viewportRef = ref<HTMLDivElement | null>(null);
const pageValue = ref(Math.max(1, props.page || 1));
const pageCount = ref(0);
const scale = ref(1.15);
const documentLoading = ref(false);
const error = ref('');
const pageStates = ref<PageState[]>([]);
const selectionStart = ref<{ pageNum: number; x: number; y: number } | null>(null);
const selectionBox = ref<SelectionBox | null>(null);
const pdfDoc = shallowRef<any>(null);

const canvasRefs = new Map<number, HTMLCanvasElement>();
const pageWrapRefs = new Map<number, HTMLElement>();
const renderTasks = new Map<number, any>();
let loadTask: any = null;
let renderGeneration = 0;
let pageObserver: IntersectionObserver | null = null;
let scrollFrame = 0;
let suppressPageWatch = false;
let suppressScaleWatch = false;

const selectionStyle = computed(() => {
  const box = selectionBox.value;
  if (!box) return {};
  return {
    left: `${box.x}px`,
    top: `${box.y}px`,
    width: `${box.width}px`,
    height: `${box.height}px`,
  };
});

watch(
  () => props.src,
  () => {
    void loadPdf();
  },
);

watch(
  () => props.page,
  (page) => {
    const nextPage = Math.max(1, page || 1);
    if (nextPage !== pageValue.value) {
      goPage(nextPage, false);
    }
  },
);

watch(scale, () => {
  if (suppressScaleWatch || !pdfDoc.value) return;
  void rebuildPagesForScale();
});

function setCanvasRef(pageNum: number, el: unknown) {
  if (el instanceof HTMLCanvasElement) {
    canvasRefs.set(pageNum, el);
  } else {
    canvasRefs.delete(pageNum);
  }
}

function setPageWrapRef(pageNum: number, el: unknown) {
  if (el instanceof HTMLElement) {
    pageWrapRefs.set(pageNum, el);
  } else {
    pageWrapRefs.delete(pageNum);
  }
}

function handlePageInput(value: number | undefined) {
  goPage(value || 1);
}

function goPage(page: number, smooth = true) {
  const max = pageCount.value || page;
  const nextPage = Math.min(Math.max(1, page), max);
  pageValue.value = nextPage;
  emit('update:page', nextPage);
  selectionBox.value = null;
  scrollToPage(nextPage, smooth);
  void renderPagesAround(nextPage);
}

function zoomIn() {
  scale.value = Math.min(3, Number((scale.value + 0.15).toFixed(2)));
}

function zoomOut() {
  scale.value = Math.max(0.5, Number((scale.value - 0.15).toFixed(2)));
}

async function fitWidth() {
  const changed = await applyFitWidthScale();
  if (!changed) {
    await rebuildPagesForScale();
  }
}

async function applyFitWidthScale() {
  const doc = pdfDoc.value;
  const container = viewportRef.value;
  if (!doc || !container) return false;
  const page = await doc.getPage(pageValue.value);
  const baseViewport = page.getViewport({ scale: 1 });
  const width = Math.max(container.clientWidth - 56, 320);
  const nextScale = Number(Math.min(3, Math.max(0.5, width / baseViewport.width)).toFixed(2));
  if (nextScale === scale.value) return false;
  scale.value = nextScale;
  return true;
}

async function loadPdf() {
  error.value = '';
  pageCount.value = 0;
  pageStates.value = [];
  canvasRefs.clear();
  pageWrapRefs.clear();
  selectionBox.value = null;
  await cleanupPdf();
  if (!props.src) return;

  documentLoading.value = true;
  try {
    loadTask = pdfjsLib.getDocument({
      url: props.src,
      httpHeaders: props.headers,
      withCredentials: false,
    });
    pdfDoc.value = await loadTask.promise;
    pageCount.value = pdfDoc.value.numPages;
    pageValue.value = Math.min(Math.max(1, props.page || 1), pageCount.value || 1);
    emit('update:page', pageValue.value);
    await nextTick();
    suppressScaleWatch = true;
    await applyFitWidthScale();
    suppressScaleWatch = false;
    await buildPageStates();
    await nextTick();
    observePages();
    scrollToPage(pageValue.value, false);
    await renderPagesAround(pageValue.value, 2);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'PDF 加载失败';
  } finally {
    suppressScaleWatch = false;
    documentLoading.value = false;
  }
}

async function buildPageStates() {
  const doc = pdfDoc.value;
  if (!doc) return;
  const nextStates: PageState[] = [];
  for (let pageNum = 1; pageNum <= doc.numPages; pageNum += 1) {
    const page = await doc.getPage(pageNum);
    const baseViewport = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: scale.value });
    nextStates.push({
      pageNum,
      width: Math.floor(viewport.width),
      height: Math.floor(viewport.height),
      pdfWidth: baseViewport.width,
      pdfHeight: baseViewport.height,
      rendered: false,
      rendering: false,
      error: '',
    });
  }
  pageStates.value = nextStates;
}

async function rebuildPagesForScale() {
  const currentPage = pageValue.value;
  renderGeneration += 1;
  await cancelRenderTasks();
  await buildPageStates();
  await nextTick();
  observePages();
  scrollToPage(currentPage, false);
  await renderPagesAround(currentPage, 2);
}

async function renderPagesAround(pageNum: number, radius = 1) {
  const pages = [];
  for (let page = Math.max(1, pageNum - radius); page <= Math.min(pageCount.value, pageNum + radius); page += 1) {
    pages.push(renderPageCanvas(page));
  }
  await Promise.all(pages);
}

async function renderPageCanvas(pageNum: number) {
  const doc = pdfDoc.value;
  const canvas = canvasRefs.get(pageNum);
  const state = pageStates.value.find((item) => item.pageNum === pageNum);
  if (!doc || !canvas || !state || state.rendered || state.rendering) return;

  const generation = renderGeneration;
  state.rendering = true;
  state.error = '';
  try {
    const page = await doc.getPage(pageNum);
    if (generation !== renderGeneration) return;
    const viewport = page.getViewport({ scale: scale.value });
    const context = canvas.getContext('2d');
    if (!context) return;

    const outputScale = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;

    const task = page.render({
      canvasContext: context,
      viewport,
      transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined,
    });
    renderTasks.set(pageNum, task);
    await task.promise;
    if (generation !== renderGeneration) return;
    state.rendered = true;
  } catch (caught) {
    if (!(caught instanceof Error) || caught.name !== 'RenderingCancelledException') {
      state.error = caught instanceof Error ? caught.message : 'PDF 渲染失败';
    }
  } finally {
    renderTasks.delete(pageNum);
    state.rendering = false;
  }
}

function observePages() {
  pageObserver?.disconnect();
  const viewport = viewportRef.value;
  if (!viewport) return;
  pageObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const pageNum = Number((entry.target as HTMLElement).dataset.pageNum);
        if (pageNum) {
          void renderPagesAround(pageNum, 1);
        }
      }
      updateCurrentPageFromScroll();
    },
    { root: viewport, rootMargin: '640px 0px', threshold: [0, 0.1, 0.5] },
  );
  for (const [pageNum, element] of pageWrapRefs) {
    element.dataset.pageNum = String(pageNum);
    pageObserver.observe(element);
  }
}

function handleViewportScroll() {
  if (scrollFrame) return;
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = 0;
    updateCurrentPageFromScroll();
  });
}

function updateCurrentPageFromScroll() {
  const viewport = viewportRef.value;
  if (!viewport || !pageStates.value.length) return;
  const viewportRect = viewport.getBoundingClientRect();
  const targetY = viewportRect.top + Math.min(160, viewportRect.height * 0.35);
  let nearestPage = pageValue.value;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const page of pageStates.value) {
    const element = pageWrapRefs.get(page.pageNum);
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    const distance = Math.abs(rect.top - targetY);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestPage = page.pageNum;
    }
  }
  if (nearestPage !== pageValue.value) {
    suppressPageWatch = true;
    pageValue.value = nearestPage;
    emit('update:page', nearestPage);
    suppressPageWatch = false;
    void renderPagesAround(nearestPage, 1);
  }
}

function scrollToPage(pageNum: number, smooth = true) {
  const viewport = viewportRef.value;
  const element = pageWrapRefs.get(pageNum);
  if (!viewport || !element) return;
  const top = element.offsetTop - 14;
  viewport.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' });
}

function handleSelectionStart(pageNum: number, event: MouseEvent) {
  if (!props.selectionEnabled || documentLoading.value || event.button !== 0) return;
  const point = eventPoint(pageNum, event);
  if (!point) return;
  event.preventDefault();
  selectionStart.value = { pageNum, x: point.x, y: point.y };
  selectionBox.value = { pageNum, x: point.x, y: point.y, width: 0, height: 0 };
  window.addEventListener('mousemove', handleSelectionMove);
  window.addEventListener('mouseup', handleSelectionEnd, { once: true });
}

function handleSelectionMove(event: MouseEvent) {
  const start = selectionStart.value;
  if (!start) return;
  const point = eventPoint(start.pageNum, event);
  if (!point) return;
  selectionBox.value = {
    pageNum: start.pageNum,
    x: Math.min(start.x, point.x),
    y: Math.min(start.y, point.y),
    width: Math.abs(point.x - start.x),
    height: Math.abs(point.y - start.y),
  };
}

function handleSelectionEnd() {
  window.removeEventListener('mousemove', handleSelectionMove);
  const box = selectionBox.value;
  selectionStart.value = null;
  if (!box || box.width < 8 || box.height < 8) {
    selectionBox.value = null;
    return;
  }
  const page = pageStates.value.find((item) => item.pageNum === box.pageNum);
  if (!page) return;
  const x0 = (box.x / Math.max(page.width, 1)) * page.pdfWidth;
  const y0 = (box.y / Math.max(page.height, 1)) * page.pdfHeight;
  const x1 = ((box.x + box.width) / Math.max(page.width, 1)) * page.pdfWidth;
  const y1 = ((box.y + box.height) / Math.max(page.height, 1)) * page.pdfHeight;
  emit('region-selected', {
    page_num: box.pageNum,
    bbox: [x0, y0, x1, y1],
    viewport_width: page.width,
    viewport_height: page.height,
    pdf_width: page.pdfWidth,
    pdf_height: page.pdfHeight,
    scale: scale.value,
  });
}

function eventPoint(pageNum: number, event: MouseEvent) {
  const wrap = pageWrapRefs.get(pageNum);
  const page = pageStates.value.find((item) => item.pageNum === pageNum);
  if (!wrap || !page) return null;
  const rect = wrap.getBoundingClientRect();
  const x = Math.min(Math.max(event.clientX - rect.left, 0), page.width);
  const y = Math.min(Math.max(event.clientY - rect.top, 0), page.height);
  return { x, y };
}

function highlightsForPage(pageNum: number) {
  return (props.highlights || []).filter((item) => item.page === pageNum);
}

function highlightStyle(highlight: Highlight) {
  return {
    left: `${highlight.x * scale.value}px`,
    top: `${highlight.y * scale.value}px`,
    width: `${highlight.width * scale.value}px`,
    height: `${highlight.height * scale.value}px`,
  };
}

function openSource() {
  const source = props.openSrc || props.src;
  window.open(`${source}#page=${pageValue.value}`, '_blank', 'noopener,noreferrer');
}

async function cancelRenderTasks() {
  const tasks = [...renderTasks.values()];
  renderTasks.clear();
  for (const task of tasks) {
    task.cancel();
    try {
      await task.promise;
    } catch {
      // ignore cancelled render
    }
  }
}

async function cleanupPdf() {
  renderGeneration += 1;
  pageObserver?.disconnect();
  pageObserver = null;
  if (scrollFrame) {
    window.cancelAnimationFrame(scrollFrame);
    scrollFrame = 0;
  }
  window.removeEventListener('mousemove', handleSelectionMove);
  await cancelRenderTasks();
  if (loadTask) {
    try {
      await loadTask.destroy();
    } catch {
      // ignore cleanup errors
    }
    loadTask = null;
  }
  if (pdfDoc.value) {
    await pdfDoc.value.destroy();
    pdfDoc.value = null;
  }
}

onMounted(loadPdf);
onBeforeUnmount(() => {
  void cleanupPdf();
});
</script>

<style scoped>
.pdf-locator {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
}

.pdf-toolbar {
  display: flex;
  min-height: 42px;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  border: 1px solid #d7dfec;
  border-radius: 10px 10px 0 0;
  background: #f8fafc;
  padding: 6px 8px;
}

.toolbar-group,
.page-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-spacer {
  flex: 1 1 auto;
}

.page-control :deep(.el-input-number) {
  width: 96px;
}

.page-control span,
.zoom-value {
  color: #4b5563;
  font-size: 13px;
  white-space: nowrap;
}

.pdf-viewport {
  position: relative;
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  overscroll-behavior: contain;
  border: 1px solid #d7dfec;
  border-top: 0;
  border-radius: 0 0 10px 10px;
  background:
    linear-gradient(rgba(30, 41, 59, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(30, 41, 59, 0.045) 1px, transparent 1px),
    #e8edf5;
  background-size: 24px 24px;
}

.page-stack {
  display: grid;
  justify-content: center;
  gap: 18px;
  min-height: 100%;
  padding: 18px 14px 28px;
}

.page-shell {
  position: relative;
  background: #fffefa;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.16);
}

.page-shell.current {
  outline: 2px solid rgba(59, 130, 246, 0.34);
  outline-offset: 4px;
}

.page-number {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 4;
  border: 1px solid rgba(203, 213, 225, 0.92);
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
  font-size: 12px;
  line-height: 22px;
  padding: 0 8px;
  pointer-events: none;
}

.pdf-canvas {
  display: block;
}

.page-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  background: rgba(248, 250, 252, 0.74);
  color: #64748b;
  font-size: 13px;
}

.page-loading.error {
  color: #b91c1c;
}

.selection-layer {
  position: absolute;
  inset: 0;
  z-index: 3;
}

.selection-layer.selecting {
  cursor: crosshair;
}

.pdf-highlight {
  position: absolute;
  z-index: 2;
  border: 2px solid #f97316;
  background: rgba(249, 115, 22, 0.16);
  pointer-events: none;
}

.pdf-highlight span {
  position: absolute;
  top: -24px;
  left: -2px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f97316;
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
}

.pdf-selection {
  position: absolute;
  z-index: 4;
  border: 2px solid #2563eb;
  background: rgba(37, 99, 235, 0.16);
  pointer-events: none;
}

.pdf-error {
  display: grid;
  gap: 12px;
  padding: 16px;
}
</style>
