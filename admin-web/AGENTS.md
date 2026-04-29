# 项目背景
刷题系统管理端，个人使用，操作题库和题目，审核 AI 解析结果。

# 技术栈
Vue3 + Vite + TypeScript + Element Plus 2.x
Pinia + vue-router 4 + axios + @vueuse/core

# 路由结构
/login                  登录
/                       重定向 /dashboard
/dashboard              首页（统计概览）
/banks                  题库列表
/banks/create           新建题库
/banks/:id/upload       上传 PDF + 解析进度
/banks/:id/review       题目审核（核心页面）
/banks/:id/questions    题目列表管理

# 全局约定
- token 存 localStorage，key: admin_token
- axios 请求头自动带 Authorization: Bearer <token>
- 响应 code !== 0 → ElMessage.error(message)
- 401 → 清除 token 跳 /login
- 接口 base URL 读 VITE_API_BASE_URL（.env 配置）
- 所有页面 <page-header> 组件展示面包屑

# 核心页面：题目审核 /banks/:id/review
功能：
- 左侧（40%）：PDF 截图/iframe 预览
- 右侧（60%）：题目列表 + 编辑面板
- 顶部筛选：全部 / 待审核（needs_review=true）/ 已发布
- 每条题目卡片：题号 + 题干截断 + 状态 tag + 操作按钮
- needs_review=true 的卡片左边框标红
- 点击题目 → 右侧展示编辑表单
- 编辑表单含：题干(textarea) + 选项ABCD + 答案(select) + 解析 + 图片预览 + AI描述(可编辑)
- 图片点击放大预览（el-image preview-teleported）
- 操作：保存 / 通过发布 / 删除
- 顶部批量通过按钮：一键发布所有 needs_review=false 的题目
