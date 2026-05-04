# MVP Local Runbook

## 1. Overview

This runbook validates the MVP path:

`upload PDF -> parse task done -> publish result -> H5 can practice questions`

Scope is local-only acceptance. It does not change parser behavior or answer-book flow.

## 2. Required Environment

### backend

Recommended local `.env` values:

```env
PORT=3010
DB_TYPE=postgres
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=password
DB_NAME=quiz_app
JWT_SECRET=dev_secret_change_me
REDIS_ENABLED=false
UPLOAD_PROVIDER=local
BACKEND_URL=http://127.0.0.1:3010
PDF_SERVICE_URL=http://127.0.0.1:8001
PDF_SERVICE_INTERNAL_TOKEN=local_pdf_internal_token_20260427
```

If not using `local`, configure one of these:

- `UPLOAD_PROVIDER=qiniu` with `QINIU_ACCESS_KEY`, `QINIU_SECRET_KEY`, `QINIU_BUCKET`, `QINIU_DOMAIN`
- `UPLOAD_PROVIDER=oss` with `OSS_REGION`, `OSS_ACCESS_KEY_ID`, `OSS_ACCESS_KEY_SECRET`, `OSS_BUCKET`

### admin-web

Create `admin-web/.env.local`:

```env
VITE_API_BASE_URL=http://127.0.0.1:3010
```

### h5-web

Create `h5-web/.env.local`:

```env
VITE_API_BASE_URL=http://127.0.0.1:3010
```

### pdf-service

If parser path needs vision/text AI, set what your current parser requires, commonly:

```env
PDF_SERVICE_INTERNAL_TOKEN=local_pdf_internal_token_20260427
DASHSCOPE_API_KEY=...
DEEPSEEK_API_KEY=...
```

## 3. Startup Order

### 3.1 pdf-service

```bash
cd pdf-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### 3.2 backend

```bash
cd backend
npm install
npm run start:dev
```

Expected port: `http://127.0.0.1:3010`

Local upload files are written under `backend/uploads/` and served from `/uploads/*`.

### 3.3 admin-web

```bash
cd admin-web
npm install
npm run dev -- --port 5173
```

### 3.4 h5-web

```bash
cd h5-web
npm install
npm run dev -- --port 5174
```

## 4. Admin Acceptance Flow

### 4.1 Upload PDF

1. Open admin: `http://127.0.0.1:5173`
2. Login with admin account
3. Go to `题库管理`
4. Open one bank and click `上传 PDF`
5. Select a PDF and click `开始上传并解析`

Expected backend calls:

- `POST /admin/upload/file`
- `POST /admin/pdf/parse`

### 4.2 Wait For Parse Task

You can watch either page:

- upload page: `/banks/:id/upload`
- task list: `/pdf/tasks`

Task is acceptable only when `status=done`.

Validation API:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:3010/admin/pdf/task/$TASK_ID"
```

### 4.3 Publish Result

1. Open `解析任务`
2. Find the `done` task
3. Click `一键发布结果`
4. Confirm the dialog

Expected backend call:

```bash
curl -X POST "http://127.0.0.1:3010/admin/pdf/task/$TASK_ID/publish-result" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"publish_bank":true}'
```

Success means response includes:

- `published_count > 0`
- `bank_status = published`
- `total_count > 0`

## 5. H5 Validation Flow

### 5.1 Check published bank exists

```bash
curl "http://127.0.0.1:3010/api/banks?page=1&pageSize=100"
```

Expected: target bank is present and `total_count > 0`.

### 5.2 Check published questions exist

```bash
curl "http://127.0.0.1:3010/api/questions?bankId=$BANK_ID&page=1&pageSize=100"
```

Expected: `list` is not empty.

### 5.3 Open H5 and practice

1. Open `http://127.0.0.1:5174`
2. Login with H5 account
3. Enter the published bank
4. Start quiz
5. Submit one answer
6. Confirm you can see result and continue to next question

Final acceptance signal:

- bank visible in H5
- quiz page loads
- at least one question can be answered
- submit returns correctness/analysis
- next question works

## 6. Optional DB / Log Checks

### parse task

- `parse_tasks.status = done`
- `parse_tasks.done_count > 0`

### bank

- `question_banks.status = published`
- `question_banks.total_count > 0`

### questions

- `questions.parse_task_id = $TASK_ID`
- `questions.status = published`

### logs

Watch backend and pdf-service logs for:

- upload failures
- parse task failures
- callback errors
- `zero_questions_extracted`

## 7. Curl Helpers

### login and save token

```bash
LOGIN=$(curl -s -X POST "http://127.0.0.1:3010/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800138000","password":"123456"}')

TOKEN=$(printf '%s' "$LOGIN" | node -e "const fs=require('fs');const data=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(data.data.access_token)")
```

### verify local upload URL is accessible

```bash
curl -I "http://127.0.0.1:3010/uploads/<relative-path-from-upload-response>"
```

## 8. Common Problems

### zero_questions_extracted

- Meaning: parser finished but did not extract usable questions
- Impact: task cannot be published into usable H5 data
- Action: switch to a known-good PDF sample or inspect parser/runtime logs

### port mismatch

- Symptom: admin/H5 page opens but API calls fail
- Check `admin-web/.env.local` and `h5-web/.env.local`
- Expected backend base URL: `http://127.0.0.1:3010`

### upload failed

- If using `UPLOAD_PROVIDER=local`, check backend is serving `/uploads/*`
- If using `qiniu` or `oss`, check full credential set exists
- Confirm `BACKEND_URL=http://127.0.0.1:3010`

### publish succeeded but H5 still empty

- Check `/api/banks` contains the bank
- Check `/api/questions?bankId=...` returns published rows
- Check `question_banks.status` is `published`
- Check `question_banks.total_count > 0`
