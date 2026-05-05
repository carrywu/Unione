# COCR-M20C: Provider Strategy

## 1. 结论

M20C 的 provider 策略不能只看 toy health report，必须以真实资料分析批量 smoke 为准。

真实多页结论：

- `qwen_vl`：真实资料分析组 `3/3` 超时，不适合无 timeout 地直接跑到底
- `volcengine_ark_vl`：在 `qwen_vl` 超时后 `3/3` 成功接管，是本轮最有效的 hedge
- `mimo_vl`：当前 `429 quota exhausted`，不能做第一备援
- `qwen-plus`：文本理解层能正确低置信拒答，适合继续做资料分析 understanding smoke
- OCR provider（百度/腾讯）：本轮 key 缺失，只能记录 `unavailable`，不宣称真实排序

## 2. Provider 矩阵

| provider | 当前状态 | 证据 | 策略 |
| --- | --- | --- | --- |
| `qwen_vl` | 可配置，toy health pass，但真实资料分析批量 `3/3 timeout` | `batch-visual-context-summary.json` | 保留 first try，但必须配短 soft-timeout |
| `volcengine_ark_vl` | remote smoke pass；真实资料分析 hedge `3/3` 成功；endpoint-id 对 responses API 仍有 `403` 风险 | `.agent/reports/provider-health-report.*`、`batch-visual-context-summary.json` | 作为资料分析 visual hedge/fallback 优先 provider；使用可工作的模型名 fallback |
| `mimo_vl` | `429 quota exhausted` | `.agent/reports/provider-health-report.*` | `skip/deprioritize` |
| `qwen-plus` | 真实文本 smoke 可用，能输出低置信拒答 / 不确定解释 | `batch-llm-understanding-summary.json` | 继续用于 understanding smoke，不直接当自动放行依据 |
| `baidu_paper_cut_edu` | key missing | `batch-ocr-summary.json` | 本轮无真实排序结论 |
| `tencent_question_split` / `layout` | key missing | `batch-ocr-summary.json` | 本轮无真实排序结论 |

## 3. 推荐顺序

### 视觉理解

1. `qwen_vl`
2. `volcengine_ark_vl`
3. `mimo_vl`

但这个顺序的前提是：

- `qwen_vl` 只拿短窗口先试
- `Ark` 必须是显式 hedge，而不是被 `mimo_vl` 顺序拖住
- `mimo_vl` 一旦出现 `429 quota exhausted`，直接降级，不参与第一备援

### 文本理解

1. `qwen-plus`
2. 其他文本模型仅在真实 key 和样本可用后再比较

### OCR

- 本轮不输出百度/腾讯真实排序
- 在拿到真实 OCR key 之前，只允许说“商业 OCR 真实多页排序未验证”

## 4. 推荐超时

资料分析 visual 建议：

- page/group soft-timeout：`12s` per provider
- overall page budget：`60s`
- `qwen_vl` 超时后立即 hedge 到 Ark

原因：

- `qwen_vl` 在 toy smoke 里快，但在真实资料分析图表页不稳定
- Ark 单次成功耗时更长，但真实批量里是有效救援路径
- 如果还让 `qwen_vl` 长时间阻塞，会把 real smoke 变成超长等待而非有效验证

## 5. Replay / 人工复核规则

使用 replay / import 的时机：

- 真实 OCR key 缺失
- 真实 OCR provider 返回 `skipped_unavailable`
- 为了验证 workbench / H5 UI，需要导入已生成的真实 smoke summary

必须转人工复核的时机：

- `bbox_source=local_parser`
- `bbox_source=tesseract_local_ocr` 且题目或表格数据不完整
- `source_material_complete=false`
- 缺表头 / 缺单位 / 缺图例 / 缺关键数据点
- `answer_conflict=true`
- 无 `calculation_reasoning` 但给出高置信答案

## 6. `.env.example` 同步

M20C 后推荐值：

```env
VISION_AI_PROVIDER_ORDER=qwen_vl,volcengine_ark_vl,mimo_vl
VISION_AI_TIMEOUT_SECONDS=60
VISION_AI_PROVIDER_TIMEOUT_SECONDS=12
PDF_VISUAL_PAGE_TIMEOUT_SECONDS=60
PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS=12
COMMERCIAL_OCR_REAL_SMOKE=false
COMMERCIAL_OCR_FIXTURE_ROOT=
```

说明：

- `COMMERCIAL_OCR_REAL_SMOKE` 默认仍保持 `false`，真实调用按限量脚本执行
- `COMMERCIAL_OCR_FIXTURE_ROOT` 是 real batch import / Playwright E2E 必需项，避免 helper 状态泄漏到默认 fixture 根

## 7. 最终策略

- 不把 `qwen_vl` 写成“稳定第一 provider”，而是“可先试，但 timeout-prone”
- 不把 `mimo_vl` 放回第一备援
- 不把 `tesseract_local_ocr` 说成商业 OCR 成功
- 在真实 OCR key 到位前，把当前多页结论定位为“真实题本 + 真实 VLM/LLM + 本地 OCR 分组兜底”的硬化结果
