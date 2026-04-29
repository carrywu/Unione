import { createRouter, createWebHistory } from 'vue-router';
import LoginView from '@/views/LoginView.vue';
import RegisterView from '@/views/RegisterView.vue';
import HomeView from '@/views/HomeView.vue';
import BankView from '@/views/BankView.vue';
import QuizView from '@/views/QuizView.vue';
import ResultView from '@/views/ResultView.vue';
import WrongView from '@/views/WrongView.vue';
import AnalysisView from '@/views/AnalysisView.vue';
import ProfileView from '@/views/ProfileView.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/register', component: RegisterView },
    { path: '/', component: HomeView },
    { path: '/bank/:id?', component: BankView },
    { path: '/quiz/:bankId', component: QuizView },
    { path: '/result', component: ResultView },
    { path: '/wrong', component: WrongView },
    { path: '/analysis', component: AnalysisView },
    { path: '/profile', component: ProfileView },
  ],
});

router.beforeEach((to) => {
  const token = localStorage.getItem('h5_token');
  const publicPaths = new Set(['/login', '/register']);
  if (!token && !publicPaths.has(to.path)) {
    return '/login';
  }
  if (token && publicPaths.has(to.path)) {
    return '/';
  }
  return true;
});

export default router;
