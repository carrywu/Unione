from __future__ import annotations

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from ai_solver.enhancer import enhance_questions_with_ai_solver, should_solve_question
from ai_solver.schema import QuestionSolvingResponse


class FakeSolverProvider:
    name = "bailian-deepseek"
    model = "deepseek-r1"

    def __init__(self, responses=None, error: Exception | None = None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def solve_question(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return QuestionSolvingResponse(
            question_id=request.question_id,
            ai_candidate_answer="C",
            ai_candidate_analysis="C 项符合题意。",
            ai_answer_confidence=0.86,
            ai_reasoning_summary="资料分析表格读取。",
            ai_knowledge_points=["资料分析", "表格读取"],
            ai_risk_flags=[],
            answer_conflict=False,
        )


def sample_questions():
    return [
        {
            "id": "q1",
            "index": 1,
            "content": "无需复查的文字题",
            "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            "answer": "A",
            "analysis": "官方解析",
            "images": [],
            "visual_refs": [],
            "image_refs": [],
            "source_page_start": 1,
            "needs_review": False,
            "parse_warnings": [],
        },
        {
            "id": "q2",
            "index": 2,
            "content": "需复查的表格题",
            "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            "answer": "A",
            "analysis": "官方解析",
            "images": [{"ref": "p2-img1", "caption": "统计表"}],
            "visual_refs": [{"id": "p2-img1", "caption": "统计表"}],
            "image_refs": ["p2-img1"],
            "ai_corrections": [{"provider": "qwen-vl", "status": "applied"}],
            "ai_review_notes": "视觉模型认为该表属于第2题",
            "source_page_start": 2,
            "needs_review": True,
            "parse_warnings": ["visual_assignment_low_confidence"],
        },
    ]


def materials():
    return [{"id": "m1", "content": "资料：统计表显示 A/B/C/D 四类指标。"}]


class AISolverEnhancementTest(unittest.TestCase):
    def test_disabled_feature_leaves_questions_unchanged(self):
        questions = sample_questions()
        original = deepcopy(questions)
        provider = FakeSolverProvider()
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "false"}, clear=False):
            result = enhance_questions_with_ai_solver(
                questions=questions,
                materials=materials(),
                provider=provider,
            )

        self.assertEqual(result.questions, original)
        self.assertEqual(provider.calls, [])
        self.assertEqual(result.stats["solved_question_ids"], [])

    def test_missing_dashscope_key_skips_without_failing(self):
        questions = sample_questions()
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "true", "DASHSCOPE_API_KEY": ""}, clear=False):
            result = enhance_questions_with_ai_solver(questions=questions, materials=materials())

        self.assertEqual(result.questions, questions)
        self.assertIn("ai_solver_api_key_missing", result.stats["warnings"])

    def test_mock_deepseek_candidate_does_not_overwrite_official_answer(self):
        provider = FakeSolverProvider(
            responses=[
                QuestionSolvingResponse(
                    question_id="q2",
                    ai_candidate_answer="C",
                    ai_candidate_analysis="A项不符合；B项不符合；C项符合；D项不符合。因此选C。",
                    ai_answer_confidence=0.86,
                    ai_reasoning_summary="本题考查资料分析中的表格读取。",
                    ai_knowledge_points=["资料分析", "表格读取"],
                    ai_risk_flags=[],
                    answer_conflict=False,
                )
            ]
        )
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "true"}, clear=False):
            result = enhance_questions_with_ai_solver(
                questions=sample_questions(),
                materials=materials(),
                provider=provider,
            )

        q2 = result.questions[1]
        self.assertEqual(q2["answer"], "A")
        self.assertEqual(q2["analysis"], "官方解析")
        self.assertEqual(q2["ai_candidate_answer"], "C")
        self.assertIn("因此选C", q2["ai_candidate_analysis"])
        self.assertEqual(q2["ai_solver_provider"], "bailian-deepseek")
        self.assertEqual(q2["ai_solver_model"], "deepseek-r1")
        self.assertIn("ai_solver_created_at", q2)

    def test_existing_answer_conflict_sets_review_warning(self):
        provider = FakeSolverProvider(
            responses=[
                QuestionSolvingResponse(
                    question_id="q2",
                    ai_candidate_answer="C",
                    ai_candidate_analysis="C 项正确。",
                    ai_answer_confidence=0.9,
                    ai_reasoning_summary="比对选项。",
                    ai_knowledge_points=["资料分析"],
                    ai_risk_flags=[],
                    answer_conflict=False,
                )
            ]
        )
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "true"}, clear=False):
            result = enhance_questions_with_ai_solver(
                questions=sample_questions(),
                materials=materials(),
                provider=provider,
            )

        q2 = result.questions[1]
        self.assertTrue(q2["ai_answer_conflict"])
        self.assertTrue(q2["needs_review"])
        self.assertIn("ai_answer_conflict", q2["parse_warnings"])

    def test_low_confidence_sets_review_warning(self):
        provider = FakeSolverProvider(
            responses=[
                QuestionSolvingResponse(
                    question_id="q2",
                    ai_candidate_answer="B",
                    ai_candidate_analysis="信息不足，只能低置信度判断。",
                    ai_answer_confidence=0.55,
                    ai_reasoning_summary="缺少表格上下文。",
                    ai_knowledge_points=["资料分析"],
                    ai_risk_flags=["missing_context"],
                    answer_conflict=False,
                )
            ]
        )
        with patch.dict(
            os.environ,
            {"ENABLE_AI_SOLVER": "true", "AI_SOLVER_CONFIDENCE_THRESHOLD": "0.7"},
            clear=False,
        ):
            result = enhance_questions_with_ai_solver(
                questions=sample_questions(),
                materials=materials(),
                provider=provider,
            )

        q2 = result.questions[1]
        self.assertTrue(q2["needs_review"])
        self.assertIn("low_ai_answer_confidence", q2["parse_warnings"])
        self.assertEqual(q2["ai_risk_flags"], ["missing_context"])

    def test_provider_error_does_not_fail_parse(self):
        provider = FakeSolverProvider(error=ValueError("invalid json"))
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "true"}, clear=False):
            result = enhance_questions_with_ai_solver(
                questions=sample_questions(),
                materials=materials(),
                provider=provider,
            )

        self.assertEqual(result.questions[0]["answer"], "A")
        self.assertIn("ai_solver_failed", result.stats["warnings"])
        self.assertIn("ai_solver_failed", result.questions[1]["parse_warnings"])

    def test_review_only_scope_solves_review_visual_or_qwen_questions(self):
        provider = FakeSolverProvider(
            responses=[
                QuestionSolvingResponse(
                    question_id="q2",
                    ai_candidate_answer="C",
                    ai_candidate_analysis="C 项正确。",
                    ai_answer_confidence=0.86,
                    ai_reasoning_summary="表格读取。",
                    ai_knowledge_points=["资料分析"],
                    ai_risk_flags=[],
                    answer_conflict=False,
                )
            ]
        )
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "true", "AI_SOLVER_SCOPE": "review_only"}, clear=False):
            result = enhance_questions_with_ai_solver(
                questions=sample_questions(),
                materials=materials(),
                provider=provider,
            )

        self.assertEqual([call.question_id for call in provider.calls], ["q2"])
        self.assertNotIn("ai_candidate_answer", result.questions[0])
        self.assertEqual(result.questions[1]["ai_candidate_answer"], "C")

    def test_all_scope_solves_all_questions(self):
        provider = FakeSolverProvider(
            responses=[
                QuestionSolvingResponse("q1", "A", "A 项正确。", 0.9, "常识判断。", ["常识判断"], [], False),
                QuestionSolvingResponse("q2", "C", "C 项正确。", 0.9, "资料分析。", ["资料分析"], [], False),
            ]
        )
        with patch.dict(os.environ, {"ENABLE_AI_SOLVER": "true", "AI_SOLVER_SCOPE": "all"}, clear=False):
            result = enhance_questions_with_ai_solver(
                questions=sample_questions(),
                materials=materials(),
                provider=provider,
            )

        self.assertEqual([call.question_id for call in provider.calls], ["q1", "q2"])
        self.assertEqual(result.questions[0]["ai_candidate_answer"], "A")
        self.assertEqual(result.questions[1]["ai_candidate_answer"], "C")

    def test_should_solve_question_scope_rules(self):
        q1, q2 = sample_questions()
        self.assertFalse(should_solve_question(q1, scope="review_only"))
        self.assertTrue(should_solve_question(q2, scope="review_only"))
        self.assertTrue(should_solve_question(q1, scope="all"))


if __name__ == "__main__":
    unittest.main()
