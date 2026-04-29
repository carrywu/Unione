import unittest
import json
from concurrent.futures import TimeoutError
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from parser_kernel.adapter import _bbox_to_page_rect, parse_extractor_with_kernel


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
            self.assertTrue(result["questions"][0]["images"])
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
            self.assertIn("material_range_uncertain", by_index[5]["parse_warnings"])
            self.assertTrue(by_index[5]["needs_review"])


if __name__ == "__main__":
    unittest.main()
