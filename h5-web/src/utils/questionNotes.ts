const NOTE_PREFIX = 'quiz-question-note:';

export function getQuestionNote(questionId?: string) {
  if (!questionId) return '';
  return localStorage.getItem(`${NOTE_PREFIX}${questionId}`) || '';
}

export function saveQuestionNote(questionId: string, note: string) {
  localStorage.setItem(`${NOTE_PREFIX}${questionId}`, note.trim());
}
