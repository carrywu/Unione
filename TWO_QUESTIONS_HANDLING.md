# 两道题的处理说明

本文说明这两道题当前在系统中的处理逻辑，便于后续询问 GPT 或继续设计审核流程。

## 涉及的两道题

### 题目 A

- 题目 ID：`54fd057b-6bf9-401f-a659-82c91fcf2e00`
- 解析任务 ID：`16b7ec7c-3140-4743-ba82-d00772d05756`

### 题目 B

- 题目 ID：`91ec66c5-0c55-4f06-84a5-911b54968756`
- 解析任务 ID：`c3886b32-9c90-4099-b358-f403005f2ee0`

## 我现在是怎么处理它们的

这两道题没有被自动合并，也没有被自动纠正来源。系统按“每道题自己的来源”处理。

处理链路是：

```text
题目 question.id
  -> 查询题目详情
  -> 读取 question.parse_task_id
  -> 查询 parse_task
  -> 找到该解析任务对应的原始 PDF
  -> 用 question.page_num 或 question.page_range[0] 定位到 PDF 页
  -> 管理员人工对照 PDF 修改题目
```

也就是说：

- 题目 A 使用解析任务 `16b7ec7c-3140-4743-ba82-d00772d05756` 对应的原 PDF。
- 题目 B 使用解析任务 `c3886b32-9c90-4099-b358-f403005f2ee0` 对应的原 PDF。
- 如果两个解析任务不同，系统默认认为它们来自两次不同的 PDF 解析。
- 即使它们实际可能来自同一个 PDF 的重复上传，当前逻辑也不会自动判断。

## 题目 ID 的作用

`question.id` 是系统中题目的唯一主键。

它用于：

- 打开题目详情页；
- 保存题干、选项、答案、解析；
- 发布或标记待审核；
- 删除题目；
- 跳转到 PDF 对照编辑页。

例如保存题目时调用：

```text
PUT /admin/questions/:id
```

其中 `:id` 就是题目 ID。

## 解析任务 ID 的作用

`question.parse_task_id` 表示这道题由哪一次 PDF 解析任务生成。

后端会用它去查 `parse_task` 表，拿到：

- 原始 PDF 地址 `file_url`
- 原始 PDF 文件名 `file_name`
- 解析任务 ID `task_id`

然后前端 PDF.js 不直接读取 `file_url`，而是读取后端代理：

```text
GET /admin/pdf/proxy/:taskId
```

这样可以避免原 PDF 地址的 CORS 或私有下载链接问题。

## PDF 定位逻辑

题目预览页打开后，右侧 PDF 初始页码按下面顺序决定：

```text
question.pdf_source.page_num
  或 question.page_num
  或 question.page_range[0]
  或 1
```

当前只做到“定位到 PDF 页”，没有做到页内框选。

## 人工修改逻辑

我已经把题目预览页改成了“PDF 对照编辑页”。

左侧可以直接修改：

- 题干；
- 选项 A/B/C/D；
- 答案；
- 解析；
- 状态：草稿 / 已发布；
- 是否仍需复查。

右侧显示该题来源解析任务对应的原 PDF，并定位到题目所在页。

保存时：

```text
PUT /admin/questions/:id
```

保存后再重新请求：

```text
GET /admin/questions/:id
```

这样可以重新拿到完整题目详情和 `pdf_source`，避免保存后 PDF 定位信息丢失。

## 当前没有做的自动处理

目前没有做这些事情：

- 没有自动判断这两道题是否重复；
- 没有自动合并不同解析任务下的题；
- 没有自动改写 `parse_task_id`；
- 没有自动判断两道题是否来自同一个 PDF；
- 没有页内坐标框选；
- 没有从 PDF 中手动框选截图并写入题目图片。

## 可以问 GPT 的核心问题

如果要继续优化，可以把问题问成：

```text
我有一个 PDF 解析题库系统。每道题保存 question.id、parse_task_id、page_num、page_range。
现在不同题目可能来自不同 parse_task，也可能是同一个 PDF 被重复解析后产生的重复题。
我希望管理端审核时能稳定定位原 PDF，并支持人工修题。
是否应该按每题 parse_task_id 定位 PDF，还是按题库统一绑定一个 PDF？
重复解析任务、重复题、题目来源纠错应该如何设计？
```

我当前采用的是保守方案：每道题按自己的 `parse_task_id` 回到自己的原 PDF，人工对照修改，不自动合并或纠错来源。
