export type PdfHighlight = {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string;
};

type PdfSource = {
  source_bbox?: number[] | null;
  source_page_start?: number | null;
  page_num?: number | null;
};

type CommercialOcrOverlay = {
  highlights?: Array<{
    page?: number;
    bbox?: number[] | null;
    label?: string;
  }>;
};

type SourceQuestion = {
  pdf_source?: PdfSource | null;
  source_bbox?: number[] | null;
  source_page_start?: number | null;
  page_num?: number | null;
  page_range?: number[] | null;
  question_quality?: {
    commercial_ocr?: {
      bbox_overlay?: CommercialOcrOverlay | null;
    } | null;
  } | null;
};

export function sourcePageForQuestion(question?: SourceQuestion | null) {
  return (
    question?.pdf_source?.source_page_start ||
    question?.source_page_start ||
    question?.pdf_source?.page_num ||
    question?.page_num ||
    question?.page_range?.[0] ||
    1
  );
}

export function buildSourceHighlights(question?: SourceQuestion | null): PdfHighlight[] {
  const overlayHighlights = question?.question_quality?.commercial_ocr?.bbox_overlay?.highlights || [];
  const normalizedOverlay: PdfHighlight[] = [];
  for (const item of overlayHighlights) {
    const bbox = item.bbox;
    if (!Array.isArray(bbox) || bbox.length !== 4) continue;
    normalizedOverlay.push({
      page: Math.max(1, Number(item.page) || sourcePageForQuestion(question)),
      x: bbox[0],
      y: bbox[1],
      width: Math.max(1, bbox[2] - bbox[0]),
      height: Math.max(1, bbox[3] - bbox[1]),
      label: item.label,
    });
  }
  if (normalizedOverlay.length) {
    return normalizedOverlay;
  }
  const bbox = question?.pdf_source?.source_bbox || question?.source_bbox;
  if (!Array.isArray(bbox) || bbox.length !== 4) return [];
  const page = question?.pdf_source?.source_page_start || question?.source_page_start || sourcePageForQuestion(question);
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
}
