export type QuestionImageSlot = 'stem' | 'options' | 'analysis' | 'material';

export interface NormalizedQuestionImage {
  src: string;
  caption?: string;
  slot: QuestionImageSlot;
}

export type RawQuestionImage =
  | string
  | {
      src?: string;
      url?: string;
      base64?: string;
      caption?: string;
      ai_desc?: string;
      role?: string;
      slot?: string;
    };

export type RawImageSource = RawQuestionImage | undefined | null;

function imageSrc(image: RawQuestionImage) {
  if (typeof image === 'string') return image;
  if (image.src) return image.src;
  if (image.url) return image.url;
  if (image.base64?.startsWith('data:')) return image.base64;
  if (image.base64) return `data:image/png;base64,${image.base64}`;
  return '';
}

function imageSlot(image: RawQuestionImage, fallback: QuestionImageSlot): QuestionImageSlot {
  if (typeof image === 'string') return fallback;
  const value = String(image.slot || image.role || '').toLowerCase();
  if (['analysis', 'explanation', '解析'].includes(value)) return 'analysis';
  if (['options', 'option', 'choice', '选项'].includes(value)) return 'options';
  if (['material', 'passage', '材料'].includes(value)) return 'material';
  if (['stem', 'question', 'content', '题干'].includes(value)) return 'stem';
  return fallback;
}

export function normalizeQuestionImages(
  images: RawQuestionImage[] | undefined,
  fallback: QuestionImageSlot = 'stem',
): NormalizedQuestionImage[] {
  return (images || [])
    .map((image) => ({
      src: imageSrc(image),
      caption: typeof image === 'string' ? undefined : image.caption || image.ai_desc,
      slot: imageSlot(image, fallback),
    }))
    .filter((image) => image.src);
}

export function questionImagesFor(
  images: RawQuestionImage[] | undefined,
  slot: QuestionImageSlot,
  fallback: QuestionImageSlot = 'stem',
) {
  return normalizeQuestionImages(images, fallback).filter((image) => image.slot === slot);
}

export function normalizeImageSources(images: RawImageSource[] | RawImageSource) {
  const list = Array.isArray(images) ? images : [images];
  return list
    .map((image) => {
      if (!image) return '';
      return imageSrc(image);
    })
    .filter(Boolean);
}
