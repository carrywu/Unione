import { existsSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { Client } from 'pg';

const DEFAULT_PREFIXES = [
  'visual-expanded-demo-',
  'visual-chain-regression-',
  'source-bbox-chain-',
  'example_',
  'admin-demo-question-book',
];

const args = process.argv.slice(2);
const apply = args.includes('--apply');
const keepBankIds = valuesFor('--keep-bank');
const keepTaskIds = valuesFor('--keep-task');
const keepArtifacts = valuesFor('--keep-artifact');

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

const client = new Client({
  host: env.DB_HOST || 'localhost',
  port: Number(env.DB_PORT || 5432),
  user: env.DB_USER || 'postgres',
  password: String(env.DB_PASS || ''),
  database: env.DB_NAME || 'quiz_app',
});

const likePatterns = DEFAULT_PREFIXES.map((prefix) => `${prefix}%`);

await client.connect();
try {
  await client.query('BEGIN');
  const { rows: banks } = await client.query(
    `SELECT id::text, name
       FROM question_banks
      WHERE name LIKE ANY($1::text[])
        AND NOT (id::text = ANY($2::text[]))
      ORDER BY created_at`,
    [likePatterns, keepBankIds],
  );
  const bankIds = banks.map((bank) => bank.id);
  const { rows: allTasks } = bankIds.length
    ? await client.query(
        `SELECT id::text, bank_id::text, file_name, file_url
           FROM parse_tasks
          WHERE bank_id::text = ANY($1::text[])
          ORDER BY created_at`,
        [bankIds],
      )
    : { rows: [] };
  const tasks = allTasks.filter((task) => !keepTaskIds.includes(task.id));
  const deleteBankIds = bankIds.filter(
    (bankId) => !allTasks.some((task) => keepTaskIds.includes(task.id) && task.bank_id === bankId),
  );
  const { rows: keptTasks } = await client.query(
    `SELECT id::text, bank_id::text, file_url
       FROM parse_tasks
      WHERE id::text = ANY($1::text[])
         OR bank_id::text = ANY($2::text[])`,
    [keepTaskIds, keepBankIds],
  );

  const counts = {
    banks: 0,
    parse_tasks: 0,
    questions: 0,
    materials: 0,
    answer_sources: 0,
    user_question_books: 0,
    user_records: 0,
    upload_source_files: 0,
    upload_task_dirs: 0,
    debug_artifacts: 0,
  };
  if (apply && deleteBankIds.length) {
    const questionIds = await client.query(
      `SELECT id::text FROM questions WHERE bank_id::text = ANY($1::text[])`,
      [deleteBankIds],
    );
    if (questionIds.rows.length) {
      const deletedRecords = await client.query(
        `DELETE FROM user_records WHERE question_id::text = ANY($1::text[])`,
        [questionIds.rows.map((row) => row.id)],
      );
      counts.user_records = deletedRecords.rowCount;
    }
    counts.answer_sources = (await client.query(
      `DELETE FROM answer_sources WHERE bank_id::text = ANY($1::text[])`,
      [deleteBankIds],
    )).rowCount;
    counts.user_question_books = (await client.query(
      `DELETE FROM user_question_books WHERE bank_id::text = ANY($1::text[])`,
      [deleteBankIds],
    )).rowCount;
    counts.questions = (await client.query(
      `DELETE FROM questions WHERE bank_id::text = ANY($1::text[])`,
      [deleteBankIds],
    )).rowCount;
    counts.materials = (await client.query(
      `DELETE FROM materials WHERE bank_id::text = ANY($1::text[])`,
      [deleteBankIds],
    )).rowCount;
    counts.parse_tasks = (await client.query(
      `DELETE FROM parse_tasks WHERE bank_id::text = ANY($1::text[]) AND NOT (id::text = ANY($2::text[]))`,
      [deleteBankIds, keepTaskIds],
    )).rowCount;
    counts.banks = (await client.query(
      `DELETE FROM question_banks WHERE id::text = ANY($1::text[])`,
      [deleteBankIds],
    )).rowCount;
  }

  const artifactDir = resolve(process.cwd(), '../pdf-service/debug_artifacts');
  const artifactMatches = existsSync(artifactDir)
    ? readdirSync(artifactDir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .filter((name) => DEFAULT_PREFIXES.some((prefix) => name.startsWith(prefix)))
        .filter((name) => !keepArtifacts.includes(name))
    : [];
  const uploadRoot = resolve(process.cwd(), 'uploads');
  const keptUploadFiles = new Set(
    keptTasks
      .map((task) => localUploadPathFromUrl(task.file_url, uploadRoot))
      .filter(Boolean)
      .map((item) => item.path),
  );
  const uploadSourceFiles = uniqueByPath(
    tasks
      .map((task) => localUploadPathFromUrl(task.file_url, uploadRoot))
      .filter(Boolean)
      .filter((item) => existsSync(item.path))
      .filter((item) => !keptUploadFiles.has(item.path)),
  );
  const uploadTaskDirs = tasks
    .map((task) => ({
      task_id: task.id,
      path: resolve(uploadRoot, 'pdf-parse', task.id),
    }))
    .filter((item) => existsSync(item.path));
  if (apply) {
    for (const item of uploadSourceFiles) {
      rmSync(item.path, { force: true });
      counts.upload_source_files += 1;
    }
    for (const item of uploadTaskDirs) {
      rmSync(item.path, { recursive: true, force: true });
      counts.upload_task_dirs += 1;
    }
    for (const name of artifactMatches) {
      rmSync(join(artifactDir, name), { recursive: true, force: true });
      counts.debug_artifacts += 1;
    }
  }

  if (apply) {
    await client.query('COMMIT');
  } else {
    await client.query('ROLLBACK');
  }

  console.log(JSON.stringify({
    mode: apply ? 'apply' : 'dry-run',
    prefixes: DEFAULT_PREFIXES,
    keep_bank_ids: keepBankIds,
    keep_task_ids: keepTaskIds,
    matched_banks: banks,
    matched_tasks: tasks,
    deleted_counts: counts,
    upload_source_files: uploadSourceFiles.map((item) => item.relative_path),
    upload_task_dirs: uploadTaskDirs.map((item) => item.task_id),
    debug_artifacts: artifactMatches,
  }, null, 2));
} catch (error) {
  await client.query('ROLLBACK');
  throw error;
} finally {
  await client.end();
}

function valuesFor(flag) {
  const values = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === flag && args[index + 1]) {
      values.push(args[index + 1]);
    }
  }
  return values;
}

function localUploadPathFromUrl(rawUrl, uploadRoot) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  let pathname = '';
  try {
    pathname = new URL(rawUrl).pathname;
  } catch {
    return null;
  }
  const marker = '/uploads/';
  const markerIndex = pathname.indexOf(marker);
  if (markerIndex < 0) return null;
  const relativePath = decodeURIComponent(pathname.slice(markerIndex + marker.length));
  if (!relativePath || relativePath.includes('\0') || relativePath.split(/[\\/]/).includes('..')) {
    return null;
  }
  const absolutePath = resolve(uploadRoot, relativePath);
  if (!absolutePath.startsWith(`${uploadRoot}/`) && absolutePath !== uploadRoot) {
    return null;
  }
  return {
    path: absolutePath,
    relative_path: relative(uploadRoot, absolutePath),
  };
}

function uniqueByPath(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    if (seen.has(item.path)) continue;
    seen.add(item.path);
    result.push(item);
  }
  return result;
}
