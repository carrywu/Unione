# Next Session

更新时间：2026-04-29

## 当前状态

本次已经把主链路推到可交付：

- 后台审核页可编辑题干、选项、答案、解析、题型和图片。
- 图片可删除、排序、移动到相邻题、修改插入位置。
- 后端和 PDF 服务都已经接入单题 AI 修复和低置信发布拦截。
- PDF 解析规则、Validator 和测试都已补一版。

## 已完成验证

- `backend`: `corepack pnpm build`
- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts`
- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-publish-export.test.ts`
- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-debug.service.test.ts`
- `admin-web`: `corepack pnpm build`
- `h5-web`: `corepack pnpm build`
- `pdf-service`: `.venv/bin/python -m unittest discover -s tests`
- `pdf-service`: `.venv/bin/python -m compileall ai_client.py main.py models.py parser_kernel pipeline.py validator.py tests/test_pdf_review_flow_rules.py`

## 继续推进建议

1. 用真实资料分析 PDF 再跑一轮完整解析，核对：
   - `资料分析题库-夸夸刷` 是否彻底不进题干。
   - 例 1-4 的图表/表格归属是否稳定。
   - 是否还有表格被拆成两张或错误合并。
2. 如果需要更强的一键表格合并，再把当前 `same_visual_group_id` 标记升级为后端实际图片拼接/重新截图。
3. 将单题 AI 修复扩展为带页面截图/bbox 的更强输入。
4. 需要时为 `review_status` 补正式数据库迁移，避免只依赖同步。

## 常用命令

```bash
cd /Users/apple/Downloads/公考/project2/backend && corepack pnpm build
cd /Users/apple/Downloads/公考/project2/backend && npx ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts
cd /Users/apple/Downloads/公考/project2/pdf-service && .venv/bin/python -m unittest discover -s tests
cd /Users/apple/Downloads/公考/project2/admin-web && corepack pnpm build
cd /Users/apple/Downloads/公考/project2/h5-web && corepack pnpm build
```

## 本轮追加完成

- 审核页已补“加入页眉页脚黑名单”入口，支持输入文本或直接使用页面选中文本。
- 审核页已补“合并下一张”按钮，当前语义是把相邻两张题图写入同一个 `same_visual_group_id`，用于连续展示和人工确认。
- 移动端预览已按 `insert_position` 分区展示题图。
- 新增并通过后端图片合并回归测试。

## 注意事项

- 工作区里还有一批既有的本地改动和未跟踪文件，不要误删或整体回滚。
- 目录里存在 `auth.json`、`题本/`、`答本/`、`backend/uploads/` 等本地数据，提交前要精确 staging，不能把敏感文件混进去。
- 下一轮如果继续做解析质量，优先从真实 PDF 回归和审核页交互补强入手，而不是继续堆新抽象层。
