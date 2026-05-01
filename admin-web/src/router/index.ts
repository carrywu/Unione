import { createRouter, createWebHistory } from 'vue-router';
import DefaultLayout from '@/layouts/DefaultLayout.vue';
import LoginView from '@/views/LoginView.vue';
import DashboardView from '@/views/DashboardView.vue';
import BankListView from '@/views/banks/BankListView.vue';
import BankCreateView from '@/views/banks/BankCreateView.vue';
import BankUploadView from '@/views/banks/BankUploadView.vue';
import BankReviewView from '@/views/banks/BankReviewView.vue';
import BankQuestionsView from '@/views/banks/BankQuestionsView.vue';
import QuestionPreviewView from '@/views/banks/QuestionPreviewView.vue';
import AnswerBookMatchView from '@/views/banks/AnswerBookMatchView.vue';
import UserListView from '@/views/users/UserListView.vue';
import TaskListView from '@/views/pdf/TaskListView.vue';
import PaperReviewView from '@/views/pdf/PaperReviewView.vue';
import MaterialListView from '@/views/materials/MaterialListView.vue';
import SystemView from '@/views/system/SystemView.vue';
import ImmersiveWorkbench from '@/views/workbench/ImmersiveWorkbench.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', component: LoginView },
    {
      path: '/',
      component: DefaultLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', component: DashboardView, meta: { title: '首页' } },
        { path: 'banks', component: BankListView, meta: { title: '题库管理' } },
        { path: 'banks/create', component: BankCreateView, meta: { title: '新建题库' } },
        { path: 'banks/:id/edit', component: BankCreateView, meta: { title: '编辑题库' } },
        { path: 'banks/:id/upload', component: BankUploadView, meta: { title: '上传 PDF' } },
        { path: 'banks/:id/answer-book', component: AnswerBookMatchView, meta: { title: '题册解析匹配' } },
        { path: 'banks/:id/review', component: BankReviewView, meta: { title: '题目审核' } },
        { path: 'banks/:id/questions', component: BankQuestionsView, meta: { title: '题目列表' } },
        { path: 'banks/:id/questions/:questionId/preview', component: QuestionPreviewView, meta: { title: '题目预览' } },
        { path: 'materials', component: MaterialListView, meta: { title: '材料管理' } },
        { path: 'pdf/tasks', component: TaskListView, meta: { title: '解析任务' } },
        { path: 'pdf/tasks/:taskId/paper-review', component: PaperReviewView, meta: { title: '制卷核对' } },
        { path: 'workbench', component: ImmersiveWorkbench, meta: { title: '沉浸式制卷' } },
        { path: 'users', component: UserListView, meta: { title: '用户管理' } },
        { path: 'system', component: SystemView, meta: { title: '系统设置' } },
      ],
    },
  ],
});

router.beforeEach((to) => {
  const token = localStorage.getItem('admin_token');
  if (!token && to.path !== '/login') {
    return '/login';
  }
  if (token && to.path === '/login') {
    return '/dashboard';
  }
  return true;
});

export default router;
