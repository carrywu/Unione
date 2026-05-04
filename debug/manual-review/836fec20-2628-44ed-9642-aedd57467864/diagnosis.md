# US-015: PDF 识别错误闭环 - 诊断报告

## 错误分类
| 类型 | 数量 | 说明 |
|------|------|------|
| answer_extraction_missing | 12 | M4 无法从题本提取答案 |
| answer_mismatch | 2 | M4 提取的答案与答本不一致 |
| analysis_differs | 14 | M4 解析与答本解析语义差异 |
| no_error (matched) | 6 | M4 与答本完全匹配 |

## 根因分析
- 题本 (题本篇.pdf) 是纯题目 PDF，不包含答案
- M4 (PDF parser) 尝试从题干推断答案，成功率 30% (6/20)
- 答本 (解析篇.pdf) 包含所有答案和解析
- M5A (answer book matching) 通过 normalized_stem_similarity 匹配，成功率为 100% (20/20)

## 识别质量检查
| 检查项 | 结果 |
|--------|------|
| 题干完整性 | ✅ 20/20 有 stem |
| 选项完整性 | ✅ 20/20 有 options A-D |
| 图片归属 | ✅ 20/20 有 visual_assets (62 张) |
| 题号连续 | ✅ 1-20 |
| 答案最终可用 | ✅ 20/20 有 final_answer_suggestion |

## 结论
- **无实际识别错误**: 题干、选项、图片全部正确提取
- **答案提取限制**: 纯题本 PDF 不含答案，M4 无法提取是预期行为
- **M5A 补偿**: 答本匹配成功率为 100%，所有答案最终可用
- **无需修复**: 当前样本无识别错误，冲突为预期行为

## 证据结构
```
debug/manual-review/836fec20-2628-44ed-9642-aedd57467864/
├── api-response.json          # 完整 paper-candidates API
├── page-understanding.json    # 页面理解数据
├── semantic-groups.json       # 语义分组
├── recrop-plan.json           # 裁切计划
├── diagnosis.md               # 本诊断报告
└── {1-20}/                    # 每题诊断
    └── diagnosis.json
```
