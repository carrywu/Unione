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

type SourceQuestion = {
  pdf_source?: PdfSource | null;
  source_bbox?: number[] | null;
  source_page_start?: number | null;
  page_num?: number | null;
  page_range?: number[] | null;
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
