import { defineStore } from 'pinia';
import { getQuestions, type Question } from '@/api/question';

export interface QuizAnswer {
  question_id: string;
  user_answer: string;
  is_correct?: boolean;
  answer?: string;
  analysis?: string;
  answer_unknown_reason?: string | null;
  analysis_unknown_reason?: string | null;
  analysis_image_url?: string;
  analysis_image_urls?: string[];
  time_spent: number;
}

export const useQuizStore = defineStore('quiz', {
  state: () => ({
    bankId: '',
    sessionMode: 'bank' as 'bank' | 'preview',
    previewPaperId: '',
    questions: [] as Question[],
    currentIndex: 0,
    answers: {} as Record<string, QuizAnswer>,
    timeLeft: 30 * 60,
    startedAt: 0,
    status: 'idle' as 'idle' | 'loading' | 'answering' | 'submitted' | 'finished',
  }),
  getters: {
    currentQuestion: (state) => state.questions[state.currentIndex],
    progress: (state) =>
      state.questions.length ? Math.round(((state.currentIndex + 1) / state.questions.length) * 100) : 0,
    isFinished: (state) => state.currentIndex >= state.questions.length - 1,
    correctCount: (state) => Object.values(state.answers).filter((answer) => answer.is_correct).length,
    wrongAnswers: (state) => Object.values(state.answers).filter((answer) => answer.is_correct === false),
  },
  actions: {
    async startQuiz(
      bankId: string,
      questions?: Question[],
      options?: { mode?: 'bank' | 'preview'; previewPaperId?: string },
    ) {
      this.status = 'loading';
      this.bankId = bankId;
      this.sessionMode = options?.mode || 'bank';
      this.previewPaperId = options?.previewPaperId || '';
      this.questions = questions || (await getQuestions(bankId, 1, 100)).list;
      this.currentIndex = 0;
      this.answers = {};
      this.timeLeft = 30 * 60;
      this.startedAt = Date.now();
      this.status = this.questions.length ? 'answering' : 'idle';
    },
    async startPreviewQuiz(paperId: string, questions: Question[]) {
      await this.startQuiz(paperId, questions, { mode: 'preview', previewPaperId: paperId });
    },
    submitAnswer(payload: QuizAnswer) {
      this.answers[payload.question_id] = payload;
      this.status = 'submitted';
    },
    nextQuestion() {
      if (this.currentIndex < this.questions.length - 1) {
        this.currentIndex += 1;
        this.status = 'answering';
      } else {
        this.finishQuiz();
      }
    },
    prevQuestion() {
      if (this.currentIndex > 0) {
        this.currentIndex -= 1;
        this.status = this.answers[this.currentQuestion.id] ? 'submitted' : 'answering';
      }
    },
    goToQuestion(index: number) {
      if (index >= 0 && index < this.questions.length) {
        this.currentIndex = index;
        const answer = this.answers[this.questions[index]?.id];
        this.status = answer ? 'submitted' : 'answering';
      }
    },
    finishQuiz() {
      this.status = 'finished';
    },
  },
});
