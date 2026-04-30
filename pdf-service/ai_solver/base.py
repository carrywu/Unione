from __future__ import annotations

from abc import ABC, abstractmethod

from ai_solver.schema import QuestionSolvingRequest, QuestionSolvingResponse


class QuestionSolverProvider(ABC):
    name = "question-solver"
    model = ""

    @abstractmethod
    def solve_question(self, request: QuestionSolvingRequest) -> QuestionSolvingResponse:
        raise NotImplementedError
