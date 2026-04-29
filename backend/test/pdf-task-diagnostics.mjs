import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { Client } from 'pg';

const taskId = process.argv[2];
const maxIndex = Number(process.argv[3] || 7);

if (!taskId) {
  console.error('Usage: node test/pdf-task-diagnostics.mjs <parse_task_id> [max_index]');
  process.exit(2);
}

const env = { ...process.env };
const envPath = join(process.cwd(), '.env');
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const index = trimmed.indexOf('=');
    if (index < 0) continue;
    const key = trimmed.slice(0, index).trim();
    let value = trimmed.slice(index + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
}

function asArray(value) {
  if (value == null || value === '') return [];
  if (Array.isArray(value)) return value;
  if (typeof value === 'object') return [value];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function asBbox(value) {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const bbox = value.map(Number);
  return bbox.every(Number.isFinite) && bbox[2] > bbox[0] && bbox[3] > bbox[1] ? bbox : null;
}

function roundBbox(bbox) {
  return bbox ? bbox.map((value) => Math.round(Number(value) * 100) / 100) : null;
}

function visualRefs(question) {
  return asArray(question.visual_refs)
    .map((item) => ({
      id: item.id || item.ref || '',
      page: item.page ?? null,
      bbox: roundBbox(asBbox(item.bbox)),
      raw_bbox: roundBbox(asBbox(item.raw_bbox)),
      expanded_bbox: roundBbox(asBbox(item.expanded_bbox)),
      absorbed_texts: asArray(item.absorbed_texts).map((text) => ({
        text: text.text || '',
        type: text.type || '',
        bbox: roundBbox(asBbox(text.bbox)),
      })),
    }))
    .filter((item) => item.id || item.bbox);
}

function images(question) {
  return asArray(question.images)
    .map((item) => typeof item === 'string'
      ? { id: item, ref: item, page: null, bbox: null, role: null }
      : {
          id: item.id || item.ref || item.url || '',
          ref: item.ref || null,
          page: item.page ?? null,
          bbox: roundBbox(asBbox(item.bbox)),
          raw_bbox: roundBbox(asBbox(item.raw_bbox)),
          expanded_bbox: roundBbox(asBbox(item.expanded_bbox)),
          absorbed_texts: asArray(item.absorbed_texts).map((text) => ({
            text: text.text || '',
            type: text.type || '',
            bbox: roundBbox(asBbox(text.bbox)),
          })),
          role: item.role || item.image_role || null,
        })
    .filter((item) => item.id || item.bbox);
}

function intersects(left, right) {
  if (!left || !right) return false;
  return Math.max(left[0], right[0]) < Math.min(left[2], right[2])
    && Math.max(left[1], right[1]) < Math.min(left[3], right[3]);
}

function options(question) {
  return {
    A: question.option_a || '',
    B: question.option_b || '',
    C: question.option_c || '',
    D: question.option_d || '',
  };
}

function visualIds(questionPayload) {
  return questionPayload.visual_refs.map((item) => item.id || item.ref).filter(Boolean);
}

function imageIds(questionPayload) {
  return questionPayload.images.map((item) => item.ref || item.id).filter(Boolean);
}

function reviewPayload(questionPayload) {
  return {
    question: {
      id: questionPayload.id,
      index_num: questionPayload.index,
      image_refs: imageIds(questionPayload),
      visual_refs: questionPayload.visual_refs,
      images: questionPayload.images,
      source_bbox_present: Object.prototype.hasOwnProperty.call(questionPayload, 'source_bbox_in_question'),
    },
    source: {
      source_page_start: questionPayload.source_page_start,
      source_page_end: questionPayload.source_page_end,
      source_bbox: questionPayload.source_bbox,
    },
  };
}

function assertion(name, pass, details = {}) {
  return { name, pass: Boolean(pass), details };
}

const client = new Client({
  host: env.DB_HOST || 'localhost',
  port: Number(env.DB_PORT || 5432),
  user: env.DB_USER || 'postgres',
  password: env.DB_PASS || '',
  database: env.DB_NAME || 'quiz_app',
});

await client.connect();
try {
  const { rows } = await client.query(
    `SELECT id::text, index_num, source_page_start, source_page_end, source_bbox,
            visual_refs, images, content, option_a, option_b, option_c, option_d
       FROM questions
      WHERE parse_task_id = $1 AND index_num BETWEEN 1 AND $2 AND deleted_at IS NULL
      ORDER BY index_num`,
    [taskId, maxIndex],
  );

  const sourceByIndex = new Map(rows.map((row) => [row.index_num, asBbox(row.source_bbox)]));
  const visuals = rows.flatMap((row) => [
    ...visualRefs(row).map((item) => ({ owner: row.index_num, ...item })),
    ...images(row).map((item) => ({ owner: row.index_num, ...item })),
  ]);

  const payload = rows.map((row) => {
    const source = asBbox(row.source_bbox);
    return {
      index: row.index_num,
      id: row.id,
      source_page_start: row.source_page_start,
      source_page_end: row.source_page_end,
      source_bbox: roundBbox(source),
      visual_refs: visualRefs(row),
      images: images(row),
      stem: String(row.content || '').slice(0, 30),
      options: options(row),
      source_bbox_overlaps_other_source_bbox: rows
        .filter((other) => other.index_num !== row.index_num && other.source_page_start === row.source_page_start)
        .filter((other) => intersects(source, sourceByIndex.get(other.index_num)))
        .map((other) => other.index_num),
      source_bbox_overlaps_non_owner_visual_bbox: visuals
        .filter((visual) => visual.owner !== row.index_num && visual.page === row.source_page_start)
        .filter((visual) => intersects(source, asBbox(visual.bbox)))
        .map((visual) => `${visual.owner}:${visual.id || visual.ref || 'visual'}`),
    };
  });

  const byIndex = new Map(payload.map((question) => [question.index, question]));
  const q1 = byIndex.get(1);
  const q2 = byIndex.get(2);
  const q3 = byIndex.get(3);
  const q4 = byIndex.get(4);
  const q5 = byIndex.get(5);
  const reviewPayloads = [q1, q2].filter(Boolean).map(reviewPayload);
  const assertions = [
    assertion(
      'q1.source_bbox_not_cover_q2_visual_bbox',
      q1 && q2 && !q2.visual_refs.some((visual) => visual.page === q1.source_page_start && intersects(q1.source_bbox, visual.bbox)),
      { q1_source_bbox: q1?.source_bbox, q2_visual_refs: q2?.visual_refs },
    ),
    assertion(
      'q2.source_bbox_not_cover_q1_source_bbox',
      q1 && q2 && !intersects(q2.source_bbox, q1.source_bbox),
      { q1_source_bbox: q1?.source_bbox, q2_source_bbox: q2?.source_bbox },
    ),
    assertion(
      'q3.source_bbox_separate_from_own_visual_bbox',
      q3 && !q3.visual_refs.some((visual) => visual.page === q3.source_page_start && intersects(q3.source_bbox, visual.bbox)),
      { q3_source_bbox: q3?.source_bbox, q3_visual_refs: q3?.visual_refs },
    ),
    assertion(
      'q4_q5_do_not_split_same_table',
      q4 && q5 && imageIds(q4).includes('p2-img2') && imageIds(q5).length === 0,
      { q4_images: q4 ? imageIds(q4) : [], q5_images: q5 ? imageIds(q5) : [] },
    ),
    assertion(
      'no_image_question_images_empty',
      q5 && q5.visual_refs.length === 0 && q5.images.length === 0,
      { q5_visual_refs: q5?.visual_refs, q5_images: q5?.images },
    ),
    assertion(
      'review_payload_source_and_visual_separated',
      reviewPayloads.length === 2
        && reviewPayloads.every((item) => Array.isArray(item.source.source_bbox))
        && reviewPayloads.every((item) => item.question.source_bbox_present === false)
        && reviewPayloads[0].question.visual_refs[0]?.id === 'p1-img1'
        && reviewPayloads[1].question.visual_refs[0]?.id === 'p1-img2',
      { review_payloads: reviewPayloads },
    ),
  ];

  console.log(JSON.stringify({ task_id: taskId, questions: payload, review_payloads: reviewPayloads, assertions }, null, 2));
} finally {
  await client.end();
}
