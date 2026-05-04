# M6B H5 移动端一致性报告

- task_id：`836fec20-2628-44ed-9642-aedd57467864`
- verdict：`M6B_PASS`
- preview_paper_id：`h5-audit-836fec20-2628-44ed-9642-aedd57467864`

## 结论

20 题预览对象在 H5 移动端的展示与 final-question/live API 保持一致，图片未横向溢出，答案与解析可正常展开。

## 验证口径

- 对照对象：
  - `final-question JSON`
  - `live API`
  - `H5 DOM`
- 对照字段：
  - `question_no`
  - `stem`
  - `options`
  - `material`
  - `answer`
  - `analysis`
  - `image asset ids`
  - `visual_summary`

## 结果

- `question_count=20`
- `failed_questions=[]`
- `screenshots_count=20`
- 每题均产出：
  - `qXX-source.png`
  - `qXX-recrop.png`
  - `qXX-final-question.json`
  - `qXX-live-api.json`
  - `qXX-h5-mobile.png`
  - `qXX-compare-summary.json`

## 移动端 smoke

- `iPhone SE`：无 placeholder、无 image overflow
- `Android Pixel`：无 placeholder、无 image overflow

## 证据

- `/home/carry/project2/debug/h5-regression/836fec20-2628-44ed-9642-aedd57467864/playwright-h5-consistency.json`
- `/home/carry/project2/debug/h5-regression/836fec20-2628-44ed-9642-aedd57467864/q01-h5-mobile.png`
- `/home/carry/project2/debug/h5-regression/836fec20-2628-44ed-9642-aedd57467864/q20-h5-mobile.png`
- `/home/carry/project2/backend/debug/m6-preview-papers/h5-audit-836fec20-2628-44ed-9642-aedd57467864.json`

## 说明

- 正式 bank H5 API 当前未挂出这 20 题，所以本轮使用 task-level preview paper 做一致性验收。
- `scripts/recompute_m6_h5_audit.mjs` 只重算比较结果，不伪造截图或 DOM 证据。
