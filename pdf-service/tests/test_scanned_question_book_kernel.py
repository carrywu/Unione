import unittest
import json
from concurrent.futures import TimeoutError
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from parser_kernel.adapter import (
    _bbox_to_page_rect,
    _visual_timeout_result,
    parse_extractor_with_kernel,
)


class FakeScannedQuestionExtractor:
    total_pages = 1
    pdf_path = "/tmp/题本篇.pdf"

    def get_page_text(self, page_num: int) -> str:
        return ""

    def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
        return "fake-page-b64"

    def get_region_screenshot(self, page_num: int, rect, padding: int = 10) -> str:
        return "fake-region-b64"

    class _FakePage:
        class _Rect:
            x0 = 0.0
            y0 = 0.0
            x1 = 1000.0
            y1 = 1400.0

        rect = _Rect()

    doc = [_FakePage()]


class ScannedQuestionBookKernelTest(unittest.TestCase):
    def test_visual_timeout_result_uses_first_configured_provider(self):
        with patch.dict(
            "os.environ",
            {
                "VISION_AI_PROVIDER_ORDER": "volcengine_ark_vl,qwen_vl",
                "ARK_API_KEY": "ark-test",
                "ARK_VISION_MODEL": "ep-ark",
                "DASHSCOPE_API_KEY": "qwen-test",
                "AI_VISUAL_MODEL": "qwen3-vl-plus",
            },
            clear=False,
        ):
            result = _visual_timeout_result(12.0)

        self.assertEqual(result["_vision_provider"], "volcengine_ark_vl")
        self.assertEqual(
            result["_vision_provider_attempts"][0]["provider"],
            "volcengine_ark_vl",
        )

    def test_visual_bbox_conversion_uses_actual_capped_render_scale(self):
        class CappedRenderExtractor(FakeScannedQuestionExtractor):
            class _FakePage:
                class _Rect:
                    x0 = 0.0
                    y0 = 0.0
                    x1 = 1000.0
                    y1 = 2000.0

                rect = _Rect()

            doc = [_FakePage()]

            def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
                return {"width": 800, "height": 1600}

        warnings: list[str] = []
        rect, normalized = _bbox_to_page_rect(
            CappedRenderExtractor(),
            0,
            [80, 160, 400, 800],
            warnings,
        )

        self.assertEqual(warnings, [])
        self.assertIsNotNone(rect)
        self.assertEqual(normalized, [100.0, 200.0, 500.0, 1000.0])

    def test_visual_bbox_conversion_reuses_render_size_per_page(self):
        class CountingRenderExtractor(FakeScannedQuestionExtractor):
            size_calls = 0

            def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
                self.size_calls += 1
                return {"width": 1000, "height": 1400}

        extractor = CountingRenderExtractor()
        warnings: list[str] = []

        _bbox_to_page_rect(extractor, 0, [10, 20, 100, 120], warnings)
        _bbox_to_page_rect(extractor, 0, [30, 40, 200, 240], warnings)

        self.assertEqual(warnings, [])
        self.assertEqual(extractor.size_calls, 1)

    def test_scanned_question_book_uses_lower_cost_vision_capture_and_records_sizes(self):
        class RecordingExtractor(FakeScannedQuestionExtractor):
            calls: list[dict[str, int | None]] = []

            def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
                self.calls.append({"dpi": dpi, "max_side": max_side})
                return "x" * 128

            def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
                return {"width": 900, "height": 1200}

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [],
                "visuals": [],
            },
        ):
            extractor = RecordingExtractor()
            parse_extractor_with_kernel(extractor, debug_dir=tmpdir)

            self.assertEqual(extractor.calls[0]["dpi"], 110)
            self.assertEqual(extractor.calls[0]["max_side"], 1600)
            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            self.assertEqual(visual_pages[0]["image_size"], {"width": 900, "height": 1200})
            self.assertEqual(visual_pages[0]["base64_size"], 128)

    def test_in_bounds_visual_bboxes_do_not_emit_clamped_warning(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [
                    {
                        "temp_id": "m1",
                        "content": "根据以下资料：材料正文",
                        "bbox": [81, 280, 810, 644],
                    }
                ],
                "questions": [
                    {
                        "index": 1,
                        "material_temp_id": "m1",
                        "content": "题干内容",
                        "bbox": [91, 688, 558, 775],
                        "stem_bbox": [91, 688, 455, 708],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [112, 722, 168, 740]},
                            {"label": "B", "text": "乙", "bbox": [427, 722, 484, 740]},
                            {"label": "C", "text": "丙", "bbox": [112, 754, 168, 772]},
                            {"label": "D", "text": "丁", "bbox": [427, 754, 484, 772]},
                        ],
                    }
                ],
                "visuals": [],
            },
        ):
            parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            self.assertNotIn("visual_bbox_clamped", visual_pages[0]["page_warnings"])

    def test_scanned_question_source_bbox_uses_text_parts_not_visual_region(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "第一题题干",
                        "bbox": [0, 300, 1000, 900],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [0, 360, 1000, 420]},
                            {"label": "B", "text": "乙", "bbox": [0, 420, 1000, 480]},
                            {"label": "C", "text": "丙", "bbox": [0, 480, 1000, 540]},
                            {"label": "D", "text": "丁", "bbox": [0, 540, 1000, 600]},
                        ],
                    }
                ],
                "visuals": [
                    {
                        "kind": "table",
                        "bbox": [0, 650, 1000, 880],
                        "caption": "下一段表格",
                        "question_index": 1,
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            question = result["questions"][0]
            self.assertEqual(question["source_bbox"], [0.0, 196.36363220214844, 654.5454711914062, 392.7272644042969])
            self.assertEqual([image["role"] for image in question["images"]], ["table"])
            self.assertEqual([ref["role"] for ref in question["visual_refs"]], ["table"])

    def test_semantic_questions_emit_real_source_text_span_and_shared_material_group(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [],
                "semantic_questions": [
                    {
                        "question_no": 6,
                        "content": "2015 年 D 省软件及信息服务业营业额同比增长约为",
                        "pages": [1],
                        "page_num": 1,
                        "stem_bbox": [80, 300, 920, 360],
                        "options_bbox": [80, 365, 920, 460],
                        "options": [
                            {"label": "A", "text": "10%", "bbox": [90, 370, 180, 390]},
                            {"label": "B", "text": "20%", "bbox": [240, 370, 330, 390]},
                            {"label": "C", "text": "30%", "bbox": [390, 370, 480, 390]},
                            {"label": "D", "text": "40%", "bbox": [540, 370, 630, 390]},
                        ],
                        "material_temp_id": "shared-m1",
                        "material_text": "2015~2018 年D 省软件及信息服务业营业额",
                    },
                    {
                        "question_no": 7,
                        "content": "2018 年 D 省软件及信息服务业营业额约为多少亿元",
                        "pages": [1],
                        "page_num": 1,
                        "stem_bbox": [80, 500, 920, 560],
                        "options_bbox": [80, 565, 920, 660],
                        "options": [
                            {"label": "A", "text": "300", "bbox": [90, 570, 180, 590]},
                            {"label": "B", "text": "400", "bbox": [240, 570, 330, 590]},
                            {"label": "C", "text": "500", "bbox": [390, 570, 480, 590]},
                            {"label": "D", "text": "600", "bbox": [540, 570, 630, 590]},
                        ],
                        "material_temp_id": "shared-m1",
                        "material_text": "2015~2018 年D 省软件及信息服务业营业额",
                    },
                ],
                "visuals": [],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            by_index = {question["index"]: question for question in result["questions"]}
            self.assertIn(7, by_index)
            self.assertEqual(
                by_index[7]["source_text_span"],
                "7. 2018 年 D 省软件及信息服务业营业额约为多少亿元\nA. 300\nB. 400\nC. 500\nD. 600",
            )
            self.assertEqual(by_index[6]["material_group_id"], by_index[7]["material_group_id"])
            self.assertEqual(by_index[7]["material_group_question_indexes"], [6, 7])
            self.assertTrue(by_index[7]["shared_material"])

            debug_dir = Path(tmpdir) / "debug"
            question_number_scan = json.loads((debug_dir / "question-number-scan.json").read_text(encoding="utf-8"))
            self.assertEqual(question_number_scan["detected_question_numbers"], [6, 7])
            self.assertEqual(question_number_scan["missing_question_numbers"], [])
            page_understanding_recovered = json.loads(
                (debug_dir / "page-understanding-recovered.json").read_text(encoding="utf-8")
            )
            self.assertEqual(page_understanding_recovered["recovered_question_numbers"], [6, 7])
            span_report = json.loads((debug_dir / "source-text-span-report.json").read_text(encoding="utf-8"))
            self.assertEqual(span_report["questions"]["7"]["source_text_span"], by_index[7]["source_text_span"])
            material_report = json.loads((debug_dir / "material-group-binding-report.json").read_text(encoding="utf-8"))
            self.assertEqual(material_report["questions"]["7"]["material_group_question_indexes"], [6, 7])
            semantic_groups = json.loads((debug_dir / "semantic-groups.json").read_text(encoding="utf-8"))
            semantic_by_no = {group["question_no"]: group for group in semantic_groups}
            self.assertEqual(semantic_by_no[7]["source_text_span"], by_index[7]["source_text_span"])
            self.assertEqual(semantic_by_no[7]["material_group_id"], by_index[7]["material_group_id"])
            self.assertEqual(semantic_by_no[7]["material_group_question_indexes"], [6, 7])

    def test_semantic_questions_bind_shared_material_from_visual_evidence_without_material_text(self):
        shared_visual = {
            "group_id": "vg_page_2_1",
            "kind": "chart",
            "bbox": [88, 348, 576, 588],
            "caption": "柱状图展示2016-2021年固定和移动数据及互联网业务收入（亿元），折线图展示其增速（%）",
        }
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [],
                "semantic_questions": [
                    {
                        "question_no": 6,
                        "content": "2021年全国电信业务实现收入的同比增长额是",
                        "pages": [1],
                        "page_num": 1,
                        "stem_bbox": [80, 670, 500, 700],
                        "options_bbox": [80, 704, 500, 760],
                        "options": [
                            {"label": "A", "text": "0.07万亿元", "bbox": [90, 710, 180, 730]},
                            {"label": "B", "text": "0.09万亿元", "bbox": [210, 710, 300, 730]},
                            {"label": "C", "text": "0.11万亿元", "bbox": [330, 710, 420, 730]},
                            {"label": "D", "text": "0.13万亿元", "bbox": [450, 710, 540, 730]},
                        ],
                        "visual_groups": [shared_visual],
                    },
                    {
                        "question_no": 7,
                        "content": "2021年全国数据及互联网业务总收入的同比增长率是",
                        "pages": [1],
                        "page_num": 1,
                        "stem_bbox": [80, 790, 500, 820],
                        "options_bbox": [80, 824, 500, 880],
                        "options": [
                            {"label": "A", "text": "4.5%", "bbox": [90, 830, 180, 850]},
                            {"label": "B", "text": "5.1%", "bbox": [210, 830, 300, 850]},
                            {"label": "C", "text": "6.2%", "bbox": [330, 830, 420, 850]},
                            {"label": "D", "text": "7.0%", "bbox": [450, 830, 540, 850]},
                        ],
                        "visual_groups": [shared_visual],
                    },
                    {
                        "question_no": 8,
                        "content": "单独材料题不应被错误绑定",
                        "pages": [1],
                        "page_num": 1,
                        "stem_bbox": [80, 900, 500, 930],
                        "options_bbox": [80, 934, 500, 990],
                        "options": [
                            {"label": "A", "text": "2016年", "bbox": [90, 940, 180, 960]},
                            {"label": "B", "text": "2017年", "bbox": [210, 940, 300, 960]},
                            {"label": "C", "text": "2020年", "bbox": [330, 940, 420, 960]},
                            {"label": "D", "text": "2021年", "bbox": [450, 940, 540, 960]},
                        ],
                        "visual_groups": [
                            {
                                "group_id": "vg_page_2_2",
                                "kind": "chart",
                                "bbox": [90, 1000, 570, 1200],
                                "caption": "另一张不共享的图表",
                            }
                        ],
                    },
                ],
                "visuals": [],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            by_index = {question["index"]: question for question in result["questions"]}
            self.assertEqual(by_index[6]["material_group_id"], by_index[7]["material_group_id"])
            self.assertEqual(by_index[6]["material_group_question_indexes"], [6, 7])
            self.assertEqual(by_index[6]["material_group_reason"], "semantic_shared_visual_material_binding")
            self.assertTrue(by_index[6]["shared_material"])
            self.assertEqual(by_index[8]["material_group_question_indexes"], [8])
            self.assertFalse(by_index[8]["shared_material"])
            self.assertIn("7. 2021年全国数据及互联网业务总收入", by_index[7]["source_text_span"])

            material_report = json.loads(
                (Path(tmpdir) / "debug" / "material-group-binding-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(material_report["questions"]["7"]["material_group_question_indexes"], [6, 7])
            semantic_groups = json.loads((Path(tmpdir) / "debug" / "semantic-groups.json").read_text(encoding="utf-8"))
            semantic_by_no = {group["question_no"]: group for group in semantic_groups}
            self.assertIn("7. 2021年全国数据及互联网业务总收入", semantic_by_no[7]["source_text_span"])
            self.assertEqual(semantic_by_no[7]["material_group_id"], by_index[7]["material_group_id"])
            self.assertEqual(semantic_by_no[7]["material_group_question_indexes"], [6, 7])

    def test_scanned_question_without_visual_keeps_images_empty(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "无图题题干",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [0, 360, 1000, 420]},
                            {"label": "B", "text": "乙", "bbox": [0, 420, 1000, 480]},
                            {"label": "C", "text": "丙", "bbox": [0, 480, 1000, 540]},
                            {"label": "D", "text": "丁", "bbox": [0, 540, 1000, 600]},
                        ],
                    }
                ],
                "visuals": [],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            question = result["questions"][0]
            self.assertEqual(question["source_bbox"], [0.0, 196.36363220214844, 654.5454711914062, 392.7272644042969])
            self.assertEqual(question["images"], [])
            self.assertEqual(question["image_refs"], [])
            self.assertEqual(question["visual_refs"], [])

    def test_scanned_question_book_retries_once_and_classifies_schema_error(self):
        attempts = 0

        def fake_visual_call(page_b64: str):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {
                    "page_type": "unknown",
                    "warnings": ["visual_schema_invalid"],
                    "materials": [],
                    "questions": [],
                    "visuals": [],
                    "schema_validation": {"invalid_root": True},
                    "raw_model_result": "not-json",
                }
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "重试后识别成功",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [],
            }

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            side_effect=fake_visual_call,
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)
            self.assertEqual(len(result["questions"]), 1)
            self.assertEqual(attempts, 2)
            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            self.assertEqual(visual_pages[0]["request_status"], "ok")
            self.assertEqual(visual_pages[0]["attempts"], 2)
            self.assertIn("visual_schema_invalid", visual_pages[0]["attempt_errors"][0]["warnings"])

    def test_scanned_question_book_writes_failed_pages_and_can_rerun_only_failures_with_cache(self):
        class ThreePageExtractor(FakeScannedQuestionExtractor):
            total_pages = 3
            doc = [
                FakeScannedQuestionExtractor._FakePage(),
                FakeScannedQuestionExtractor._FakePage(),
                FakeScannedQuestionExtractor._FakePage(),
            ]

            def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
                return f"page-{page_num + 1}-b64"

        calls: list[str] = []

        def first_run(page_b64: str):
            calls.append(page_b64)
            if page_b64 == "page-2-b64":
                raise TimeoutError()
            page_num = int(page_b64.removeprefix("page-").removesuffix("-b64"))
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": page_num,
                        "content": f"第{page_num}页题干",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [],
            }

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            side_effect=first_run,
        ):
            first_result = parse_extractor_with_kernel(ThreePageExtractor(), debug_dir=tmpdir)
            self.assertEqual({question["index"] for question in first_result["questions"]}, {1, 3})
            failed_pages = json.loads(Path(tmpdir, "debug", "failed_pages.json").read_text(encoding="utf-8"))
            self.assertEqual(failed_pages["failed_pages"], [2])
            self.assertTrue(Path(tmpdir, "debug", "visual_page_cache", "page_1.json").exists())
            self.assertTrue(Path(tmpdir, "debug", "visual_page_cache", "page_3.json").exists())

            calls.clear()

            def rerun(page_b64: str):
                calls.append(page_b64)
                return {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [
                        {
                            "index": 2,
                            "content": "第二页续跑成功",
                            "bbox": [0, 300, 1000, 600],
                            "stem_bbox": [0, 300, 1000, 360],
                            "option_a": "甲",
                            "option_b": "乙",
                            "option_c": "丙",
                            "option_d": "丁",
                        }
                    ],
                    "visuals": [],
                }

            with patch("parser_kernel.adapter.ai_client.parse_page_visual", side_effect=rerun):
                rerun_result = parse_extractor_with_kernel(
                    ThreePageExtractor(),
                    debug_dir=tmpdir,
                    retry_failed_pages_only=True,
                )

            self.assertEqual(calls, ["page-2-b64"])
            self.assertEqual([question["index"] for question in rerun_result["questions"]], [2])
            failed_pages = json.loads(Path(tmpdir, "debug", "failed_pages.json").read_text(encoding="utf-8"))
            self.assertEqual(failed_pages["failed_pages"], [])

    def test_completed_pages_are_reused_from_checkpoint_without_retry_flag(self):
        class SevenPageExtractor(FakeScannedQuestionExtractor):
            total_pages = 7
            doc = [FakeScannedQuestionExtractor._FakePage() for _ in range(7)]

            def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
                return f"page-{page_num + 1}-b64"

        def first_run(page_b64: str):
            page_num = int(page_b64.removeprefix("page-").removesuffix("-b64"))
            if page_num == 7:
                raise TimeoutError()
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": page_num,
                        "content": f"第{page_num}页题干",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [],
            }

        rerun_calls: list[str] = []

        def rerun(page_b64: str):
            rerun_calls.append(page_b64)
            page_num = int(page_b64.removeprefix("page-").removesuffix("-b64"))
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": page_num,
                        "content": f"恢复第{page_num}页题干",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [],
            }

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            side_effect=first_run,
        ):
            first_result = parse_extractor_with_kernel(SevenPageExtractor(), debug_dir=tmpdir)
            self.assertEqual({question["index"] for question in first_result["questions"]}, {1, 2, 3, 4, 5, 6})

            with patch("parser_kernel.adapter.ai_client.parse_page_visual", side_effect=rerun):
                rerun_result = parse_extractor_with_kernel(SevenPageExtractor(), debug_dir=tmpdir)

            self.assertEqual(rerun_calls, ["page-7-b64"])
            self.assertEqual({question["index"] for question in rerun_result["questions"]}, {1, 2, 3, 4, 5, 6, 7})
            recovery_reports = list(Path(tmpdir, "debug", "recovery").glob("*/checkpoint-recovery.json"))
            self.assertTrue(recovery_reports)
            recovery_payload = json.loads(recovery_reports[-1].read_text(encoding="utf-8"))
            reused_pages = {
                item["page_no"]
                for item in recovery_payload["actions"]
                if item["action"] == "reuse_success_artifact"
            }
            self.assertEqual(reused_pages, {1, 2, 3, 4, 5, 6})

    def test_half_written_checkpoint_cache_is_not_treated_as_success(self):
        class OnePageExtractor(FakeScannedQuestionExtractor):
            total_pages = 1
            doc = [FakeScannedQuestionExtractor._FakePage()]

            def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
                return "page-1-b64"

        def success_result():
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "第一页题干",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [],
            }

        rerun_calls: list[str] = []
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value=success_result(),
        ):
            parse_extractor_with_kernel(OnePageExtractor(), debug_dir=tmpdir)
            cache_file = Path(tmpdir, "debug", "visual_page_cache", "page_1.json")
            cache_file.write_text('{"visual_result":', encoding="utf-8")

            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                side_effect=lambda page_b64: rerun_calls.append(page_b64) or success_result(),
            ):
                rerun_result = parse_extractor_with_kernel(OnePageExtractor(), debug_dir=tmpdir)

        self.assertEqual(rerun_calls, ["page-1-b64"])
        self.assertEqual([question["index"] for question in rerun_result["questions"]], [1])

    def test_stale_running_checkpoint_page_reruns_and_writes_recovery_report(self):
        class OnePageExtractor(FakeScannedQuestionExtractor):
            total_pages = 1
            doc = [FakeScannedQuestionExtractor._FakePage()]

            def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
                return "page-1-b64"

        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir, "debug", "checkpoint-manifest.json")
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "parse_checkpoint_v1",
                        "updated_at": "2026-05-01T00:00:00+00:00",
                        "total_pages": 1,
                        "pages": {
                            "1": {
                                "page_no": 1,
                                "status": "running",
                                "stage": "page_understood",
                                "attempts": 1,
                                "updated_at": "2026-05-01T00:00:00+00:00",
                            }
                        },
                        "artifacts": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            calls: list[str] = []
            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                side_effect=lambda page_b64: calls.append(page_b64)
                or {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [
                        {
                            "index": 1,
                            "content": "恢复后的第一页题干",
                            "bbox": [0, 300, 1000, 600],
                            "stem_bbox": [0, 300, 1000, 360],
                            "option_a": "甲",
                            "option_b": "乙",
                            "option_c": "丙",
                            "option_d": "丁",
                        }
                    ],
                    "visuals": [],
                },
            ):
                parse_extractor_with_kernel(OnePageExtractor(), debug_dir=tmpdir)

            self.assertEqual(calls, ["page-1-b64"])
            recovery_reports = list(Path(tmpdir, "debug", "recovery").glob("*/checkpoint-recovery.json"))
            self.assertTrue(recovery_reports)
            recovery_payload = json.loads(recovery_reports[-1].read_text(encoding="utf-8"))
            self.assertTrue(
                any(
                    item["action"] == "rerun_from_checkpoint" and item["reason"] == "stale_running_page"
                    for item in recovery_payload["actions"]
                )
            )

    def test_scanned_question_book_timeout_degrades_per_page_without_crashing_book(self):
        class TwoPageExtractor(FakeScannedQuestionExtractor):
            total_pages = 2
            doc = [FakeScannedQuestionExtractor._FakePage(), FakeScannedQuestionExtractor._FakePage()]

            def get_page_screenshot(self, page_num: int, dpi: int = 150) -> str:
                return "fake-page-b64" if page_num == 0 else "fake-page-b64-page2"

        def fake_visual_call(page_b64: str):
            if page_b64 == "fake-page-b64":
                raise TimeoutError()
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 2,
                        "content": "第二页第一题",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [0, 360, 1000, 420]},
                            {"label": "B", "text": "乙", "bbox": [0, 420, 1000, 480]},
                            {"label": "C", "text": "丙", "bbox": [0, 480, 1000, 540]},
                            {"label": "D", "text": "丁", "bbox": [0, 540, 1000, 600]},
                        ],
                    }
                ],
                "visuals": [],
            }

        extractor = TwoPageExtractor()

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            side_effect=fake_visual_call,
        ):
            result = parse_extractor_with_kernel(
                extractor,
                debug_dir=tmpdir,
            )
            self.assertEqual(result["pdf_kind"], "scanned_question_book")
            self.assertGreaterEqual(len(result["questions"]), 1)
            warnings = json.loads(Path(tmpdir, "debug", "warnings.json").read_text(encoding="utf-8"))
            parser_warnings = warnings.get("parser_warnings") or []
            self.assertTrue(any("vision_page_timeout" in item.get("warnings", []) for item in parser_warnings))
            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            timeout_page = visual_pages[0]
            self.assertIn("vision_page_timeout", timeout_page.get("page_warnings", []))
            self.assertTrue(any(region.get("type") == "page_fallback" for region in timeout_page.get("regions", [])))

    def test_semantic_questions_keep_real_source_page_numbers(self):
        class ThreePageExtractor(FakeScannedQuestionExtractor):
            total_pages = 3
            doc = [
                FakeScannedQuestionExtractor._FakePage(),
                FakeScannedQuestionExtractor._FakePage(),
                FakeScannedQuestionExtractor._FakePage(),
            ]

            def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
                return f"page-{page_num + 1}-b64"

        def fake_visual_call(page_b64: str):
            page_num = int(page_b64.removeprefix("page-").removesuffix("-b64"))
            if page_num == 2:
                return {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [
                        {
                            "index": 5,
                            "content": "第二页题目",
                            "bbox": [0, 100, 1000, 260],
                            "stem_bbox": [0, 100, 1000, 160],
                            "option_a": "甲",
                            "option_b": "乙",
                            "option_c": "丙",
                            "option_d": "丁",
                        }
                    ],
                    "visuals": [],
                }
            if page_num == 3:
                return {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [
                        {
                            "index": 8,
                            "content": "第三页题目",
                            "bbox": [0, 200, 1000, 360],
                            "stem_bbox": [0, 200, 1000, 260],
                            "option_a": "甲",
                            "option_b": "乙",
                            "option_c": "丙",
                            "option_d": "丁",
                        }
                    ],
                    "visuals": [],
                }
            return {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [],
                "visuals": [],
            }

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            side_effect=fake_visual_call,
        ):
            result = parse_extractor_with_kernel(ThreePageExtractor(), debug_dir=tmpdir)
            by_index = {item["index"]: item for item in result["questions"]}

            self.assertEqual(by_index[5]["page_num"], 2)
            self.assertEqual(by_index[5]["source_page_start"], 2)
            self.assertEqual(by_index[5]["source_page_end"], 2)
            self.assertEqual(by_index[8]["page_num"], 3)
            self.assertEqual(by_index[8]["source_page_start"], 3)
            self.assertEqual(by_index[8]["source_page_end"], 3)

    def test_scanned_question_book_visual_result_flows_into_kernel_output(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [
                    {
                        "temp_id": "m1",
                        "content": "根据以下资料，回答1-5题\n2024年全市工业产值增长。",
                        "bbox": [0, 0, 1000, 300],
                    }
                ],
                "questions": [
                    {
                        "index": 1,
                        "material_temp_id": "m1",
                        "content": "第一题题干",
                        "bbox": [0, 300, 1000, 600],
                        "stem_bbox": [0, 300, 1000, 360],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [0, 360, 1000, 420]},
                            {"label": "B", "text": "乙", "bbox": [0, 420, 1000, 480]},
                            {"label": "C", "text": "丙", "bbox": [0, 480, 1000, 540]},
                            {"label": "D", "text": "丁", "bbox": [0, 540, 1000, 600]},
                        ],
                    }
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [700, 0, 980, 260],
                        "caption": "工业产值图表",
                        "material_temp_id": "m1",
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(
                FakeScannedQuestionExtractor(),
                debug_dir=tmpdir,
            )
            self.assertEqual(result["pdf_kind"], "scanned_question_book")
            self.assertEqual(len(result["questions"]), 1)
            self.assertEqual(result["questions"][0]["index"], 1)
            self.assertEqual(result["questions"][0]["page_num"], 1)
            self.assertEqual(result["questions"][0]["source_page_start"], 1)
            self.assertEqual(result["questions"][0]["source_page_end"], 1)
            self.assertTrue(result["questions"][0]["source_bbox"])
            self.assertEqual(result["questions"][0]["option_a"], "甲")
            self.assertTrue(result["questions"][0]["images"])
            self.assertTrue(result["materials"])
            self.assertTrue(Path(tmpdir, "debug", "visual_pages.json").exists())
            self.assertTrue(Path(tmpdir, "debug", "page_elements.json").exists())
            self.assertTrue(Path(tmpdir, "debug", "question_groups.json").exists())
            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            self.assertIn("raw_result", visual_pages[0])
            self.assertIn("normalized_result", visual_pages[0])
            self.assertIn("schema_validation", visual_pages[0])
            self.assertTrue(visual_pages[0]["regions"])

    def test_scanned_question_book_invalid_bbox_degrades_without_crashing(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": ["visual_regions_dropped"],
                "schema_validation": {"dropped_question_count": 0},
                "raw_model_result": {"raw": True},
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "第一题题干",
                        "bbox": [-500, -500, 90000, 90000],
                        "stem_bbox": None,
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [-10, -10, 99999, 99999]},
                        ],
                    }
                ],
                "visuals": [],
            },
        ):
            result = parse_extractor_with_kernel(
                FakeScannedQuestionExtractor(),
                debug_dir=tmpdir,
            )
            self.assertEqual(len(result["questions"]), 1)
            self.assertEqual(result["questions"][0]["index"], 1)
            self.assertEqual(result["questions"][0]["images"], [])
            self.assertIsNone(result["questions"][0]["source_bbox"])
            warnings = json.loads(Path(tmpdir, "debug", "warnings.json").read_text(encoding="utf-8"))
            parser_warnings = warnings.get("parser_warnings") or []
            self.assertTrue(any("visual_bbox_clamped" in item.get("warnings", []) for item in parser_warnings))
            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            self.assertTrue(any("page_warnings" in page for page in visual_pages))

    def test_question_before_material_on_same_page_is_backfilled_with_low_confidence_warning(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [
                    {
                        "temp_id": "m1",
                        "content": "2024年电信业务收入情况如下。[图表]",
                        "bbox": [0, 650, 1000, 1050],
                    }
                ],
                "questions": [
                    {
                        "index": 5,
                        "content": "能够从上述材料中推出的是：",
                        "bbox": [0, 200, 1000, 520],
                        "stem_bbox": [0, 200, 1000, 260],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": [
                            {"label": "A", "text": "甲", "bbox": [0, 260, 1000, 320]},
                            {"label": "B", "text": "乙", "bbox": [0, 320, 1000, 380]},
                            {"label": "C", "text": "丙", "bbox": [0, 380, 1000, 440]},
                            {"label": "D", "text": "丁", "bbox": [0, 440, 1000, 500]},
                        ],
                    },
                    {
                        "index": 6,
                        "material_temp_id": "m1",
                        "content": "2024年业务收入同比增长额约为：",
                        "bbox": [0, 1080, 1000, 1320],
                        "stem_bbox": [0, 1080, 1000, 1140],
                        "option_a": "11",
                        "option_b": "12",
                        "option_c": "13",
                        "option_d": "14",
                        "options": [
                            {"label": "A", "text": "11", "bbox": [0, 1140, 1000, 1190]},
                            {"label": "B", "text": "12", "bbox": [0, 1190, 1000, 1240]},
                            {"label": "C", "text": "13", "bbox": [0, 1240, 1000, 1280]},
                            {"label": "D", "text": "14", "bbox": [0, 1280, 1000, 1320]},
                        ],
                    },
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [600, 700, 980, 1020],
                        "caption": "收入图",
                        "material_temp_id": "m1",
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(
                FakeScannedQuestionExtractor(),
                debug_dir=tmpdir,
            )
            by_index = {item["index"]: item for item in result["questions"]}
            self.assertEqual(by_index[5]["material_temp_id"], by_index[6]["material_temp_id"])
            self.assertEqual(by_index[5]["material_group_id"], by_index[6]["material_group_id"])
            self.assertEqual(by_index[5]["material_group_question_indexes"], [5, 6])
            self.assertTrue(by_index[5]["shared_material"])
            self.assertIn("material_range_uncertain", by_index[5]["parse_warnings"])
            self.assertTrue(by_index[5]["needs_review"])

    def test_shared_material_group_links_chart_to_following_questions(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 3,
                        "content": "根据图表可以推出的是哪一项",
                        "bbox": [0, 320, 1000, 520],
                        "stem_bbox": [0, 320, 1000, 370],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                    {
                        "index": 4,
                        "content": "根据图表计算增长率约为多少",
                        "bbox": [0, 560, 1000, 760],
                        "stem_bbox": [0, 560, 1000, 610],
                        "option_a": "10%",
                        "option_b": "20%",
                        "option_c": "30%",
                        "option_d": "40%",
                    },
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [100, 80, 900, 280],
                        "caption": "产量变化图",
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            by_index = {item["index"]: item for item in result["questions"]}
            self.assertEqual(by_index[3]["material_group_id"], by_index[4]["material_group_id"])
            self.assertEqual(by_index[3]["material_group_question_indexes"], [3, 4])
            self.assertTrue(by_index[3]["shared_material"])
            self.assertEqual(by_index[3]["material_group_reason"], "downward_visual_group")

            visual_pages = json.loads(Path(tmpdir, "debug", "visual_pages.json").read_text(encoding="utf-8"))
            material_groups = visual_pages[0]["material_groups"]
            self.assertEqual(len(material_groups), 1)
            self.assertEqual(material_groups[0]["question_indexes"], [3, 4])
            self.assertEqual(material_groups[0]["visual_bbox_list"], [[100.0, 80.0, 900.0, 280.0]])

    def test_shared_material_group_stops_at_next_chart(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "第一张图对应的问题",
                        "bbox": [0, 220, 1000, 360],
                        "stem_bbox": [0, 220, 1000, 260],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                    {
                        "index": 2,
                        "content": "第二张图对应的问题",
                        "bbox": [0, 620, 1000, 780],
                        "stem_bbox": [0, 620, 1000, 660],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                ],
                "visuals": [
                    {"kind": "chart", "bbox": [100, 40, 900, 180], "caption": "图一"},
                    {"kind": "chart", "bbox": [100, 420, 900, 580], "caption": "图二"},
                ],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            by_index = {item["index"]: item for item in result["questions"]}
            self.assertNotEqual(by_index[1]["material_group_id"], by_index[2]["material_group_id"])
            self.assertEqual(by_index[1]["material_group_question_indexes"], [1])
            self.assertEqual(by_index[2]["material_group_question_indexes"], [2])

    def test_shared_material_group_far_question_warns_without_binding(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 9,
                        "content": "距离图表很远的问题不应强行绑定",
                        "bbox": [0, 1050, 1000, 1240],
                        "stem_bbox": [0, 1050, 1000, 1100],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [100, 40, 900, 180],
                        "caption": "较远图表",
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            question = result["questions"][0]
            self.assertIsNone(question.get("material_group_id"))
            self.assertFalse(question.get("shared_material"))
            warnings = json.loads(Path(tmpdir, "debug", "warnings.json").read_text(encoding="utf-8"))
            visual_link_warnings = warnings.get("visual_link_warnings") or []
            self.assertTrue(
                any(item.get("warning") == "material_group_range_uncertain" for item in visual_link_warnings)
            )

    def test_shared_material_group_gap_uses_rendered_image_height(self):
        class ShortPdfTallRenderExtractor(FakeScannedQuestionExtractor):
            class _FakePage:
                class _Rect:
                    x0 = 0.0
                    y0 = 0.0
                    x1 = 1000.0
                    y1 = 500.0

                rect = _Rect()

            doc = [_FakePage()]

            def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
                return {"width": 1000, "height": 1600}

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "图后第一题应正常归组",
                        "bbox": [0, 600, 1000, 740],
                        "stem_bbox": [0, 600, 1000, 640],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                    {
                        "index": 2,
                        "content": "图后第二题应共享同一组",
                        "bbox": [0, 780, 1000, 920],
                        "stem_bbox": [0, 780, 1000, 820],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [100, 120, 900, 300],
                        "caption": "高分辨率渲染图",
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(ShortPdfTallRenderExtractor(), debug_dir=tmpdir)

            by_index = {item["index"]: item for item in result["questions"]}
            self.assertEqual(by_index[1]["material_group_id"], by_index[2]["material_group_id"])
            self.assertTrue(by_index[1]["shared_material"])
            warnings = json.loads(Path(tmpdir, "debug", "warnings.json").read_text(encoding="utf-8"))
            visual_link_warnings = warnings.get("visual_link_warnings") or []
            self.assertFalse(
                any(item.get("warning") == "material_group_range_uncertain" for item in visual_link_warnings)
            )

    def test_question_linked_visual_is_not_used_as_shared_material_seed(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "第一题有自己的配图",
                        "bbox": [0, 320, 1000, 500],
                        "stem_bbox": [0, 320, 1000, 370],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                    {
                        "index": 2,
                        "content": "第二题不应继承第一题配图",
                        "bbox": [0, 540, 1000, 720],
                        "stem_bbox": [0, 540, 1000, 590],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    },
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [100, 80, 900, 280],
                        "caption": "只属于第一题的图",
                        "question_index": 1,
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

            by_index = {item["index"]: item for item in result["questions"]}
            self.assertIsNone(by_index[1].get("material_group_id"))
            self.assertIsNone(by_index[2].get("material_group_id"))
            self.assertFalse(by_index[1].get("shared_material"))
            self.assertFalse(by_index[2].get("shared_material"))
            self.assertTrue(by_index[1]["images"])


if __name__ == "__main__":
    unittest.main()
