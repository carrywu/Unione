# Commercial OCR Main Handoff

当前主线已切换到 `main`，主题为 `commercial OCR first + VLM/LLM semantic assembler`。

## 当前事实

- merge 来源分支：`ralph/xingce-e2e-git-hygiene-delivery`
- merge commit：`d411a90`
- merge 后 hygiene commit：`2fbf506`
- 当前开发策略：继续直接在 `main` 上推进，默认不再新建测试分支

## 本轮已完成

- 安全合并验证分支到 `main`
- 从 Git index 中移除误跟踪的 `debug/**` runtime/raw response
- 新增 `pdf-service/commercial_ocr` provider abstraction
- 接入 provider 选择、fallback 顺序、mock provider、百度 `paper_cut_edu` adapter、腾讯 stub
- 新增 COCR M0/M1 报告与新 `prd.json`

## 真实 provider 结论

- provider：百度 `paper_cut_edu`
- endpoint：`https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu`
- auth：AK/SK 换 `access_token`，也支持 `BAIDU_ACCESS_TOKEN` 直传
- 真实 smoke：成功，第一页返回 33 个 normalized blocks
- 本地 raw trace：`/tmp/cocr-baidu-smoke/debug/commercial_ocr/cocr-baidu-smoke-success.json`

## 必看文件

- `/home/carry/project2/docs/commercial-ocr-phase-reports/COCR-M0-baseline.md`
- `/home/carry/project2/docs/commercial-ocr-phase-reports/COCR-M1-merge-main-and-provider-baseline.md`
- `/home/carry/project2/docs/commercial-ocr-phase-reports/README.md`
- `/home/carry/project2/.agent/reports/commercial-ocr-main-handoff.md`

## 继续推进建议

1. 先补 `backend pnpm build` 与 `pdf-service .venv` 全量测试结果。
2. 进入 M2/M3：用真实 OCR blocks + visual summary 做 semantic assembler。
3. 优先打通 `17-20` 共用材料题。
4. 在 M7 前不要把 `question_count == expected_count` 当成功判定。
