# 项目背景
刷题 H5，适配微信内置浏览器 + 手机浏览器。
用户可浏览题库、答题、查看错题本。

# 技术栈
Vue3 + Vite + TypeScript + Vant 4
Pinia + vue-router 4 + axios

# 路由结构
/login              手机号登录
/                   首页（题库列表，按科目分组）
/bank/:id           题库详情
/quiz/:bankId       答题页
/result             答题结果页
/wrong              错题本
/profile            个人中心

# 适配规范
- viewport: width=device-width, initial-scale=1, maximum-scale=1
- 最大宽度 750px，body 居中
- 底部安全区：padding-bottom: env(safe-area-inset-bottom)
- 主色调：#4A90D9（蓝色，类粉笔风格）

# 答题页逻辑（核心）
状态机：
  idle → loading → answering → submitted → finished
answering：显示题目，选项高亮选中
submitted：显示对错（选项变色），显示解析，"下一题"按钮
finished：跳结果页

倒计时：每套题 30 分钟，到时自动提交
进度：顶部展示"当前题/总题数"进度条

图片题：
  - van-image 展示图片，lazy-load
  - 点击 showImagePreview 全屏查看
  - 材料题：材料内容折叠在题干上方，点击展开

离线缓存：
  - 答题记录先存 localStorage（key: quiz_records_{bankId}）
  - 网络恢复后自动同步（POST /api/records/batch-submit）

# 接口 base URL
读 VITE_API_BASE_URL（.env）
