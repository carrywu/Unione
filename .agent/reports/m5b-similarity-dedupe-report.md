# M5B Similarity / Duplicate 报告

- task_id：`836fec20-2628-44ed-9642-aedd57467864`
- verdict：`M5B_PASS`

## 结论

backend 已从“空状态占位”升级为真实历史题库 similarity / duplicate 候选生成；admin-web 审核页已展示真实候选明细，不再伪造 `M5B_FAIL`。

## 本次完成

- `backend/src/modules/pdf/pdf.service.ts`
  - 基于历史题库真实 `Question` 数据生成相似候选
  - 复用既有文本归一化口径
  - 输出 `duplicate / near / sibling / similar`
  - 返回 `canonical_question_id`、`similarity_score`、`evidence` 级候选信息
- `backend/test/pdf-review-workflow.test.ts`
  - 补充真实 similarity candidate 回归测试
  - 保留空历史题库场景测试
- `admin-web/src/api/pdf.ts`
  - 扩展 `m5_similarity.similarity_candidates` 类型
- `admin-web/src/views/pdf/PaperReviewView.vue`
  - 展示真实历史题候选、分数、来源页、状态与摘要

## 验证

- `cd /home/carry/project2/backend && node -r ts-node/register -r tsconfig-paths/register test/pdf-review-workflow.test.ts`
- `cd /home/carry/project2/backend && npm run build`
- `cd /home/carry/project2/admin-web && npm run build`

## 风险边界

- 当前实现为 staged 版本：真实历史题库检索已接入，但尚未扩展到 `pgvector` / `pHash`
- `M5A` 真实答本对撞尚未完成，下一步需直接读取 `/home/carry/答本`
