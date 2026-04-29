import json
import unittest
import base64
import csv
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from tools.visual_api_smoke import parse_page_spec, run_visual_api_smoke


def _png_base64(width: int = 400, height: int = 500) -> str:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class FakeSmokeExtractor:
    total_pages = 5
    pdf_path = "/tmp/题本篇.pdf"

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.closed = False
        self.region_calls: list[dict[str, object]] = []

    def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
        self.last_capture = {"page_num": page_num, "dpi": dpi, "max_side": max_side}
        return _png_base64()

    def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
        return {"width": 400, "height": 500}

    def get_region_screenshot(self, page_num: int, rect, padding: int = 10) -> str:
        self.region_calls.append({"page_num": page_num, "rect": rect, "padding": padding})
        return f"region-page-{page_num}-padding-{padding}"

    def get_page_text(self, page_num: int) -> str:
        return ""

    def close(self) -> None:
        self.closed = True

    class _FakePage:
        class _Rect:
            x0 = 0.0
            y0 = 0.0
            x1 = 400.0
            y1 = 500.0

        rect = _Rect()

    doc = [_FakePage(), _FakePage(), _FakePage(), _FakePage(), _FakePage()]


class LargeFakeSmokeExtractor(FakeSmokeExtractor):
    total_pages = 300
    doc = [FakeSmokeExtractor._FakePage() for _ in range(total_pages)]


class VisualApiSmokeToolTest(unittest.TestCase):
    def test_parse_page_spec_supports_compat_count_ranges_and_lists(self):
        self.assertEqual(parse_page_spec("5", total_pages=100), [0, 1, 2, 3, 4])
        self.assertEqual(parse_page_spec("0-20", total_pages=100), list(range(20)))
        self.assertEqual(parse_page_spec("8,9,10", total_pages=100), [8, 9, 10])

    def test_visual_smoke_writes_required_artifacts_and_summary(self):
        def fake_kernel_parse(extractor, *, page_limit, debug_dir, retry_failed_pages_only=False):
            debug = Path(debug_dir) / "debug"
            debug.mkdir(parents=True, exist_ok=True)
            (debug / "visual_pages.json").write_text(
                json.dumps(
                    [
                        {
                            "page_num": 1,
                            "raw_result": {
                                "materials": [
                                    {
                                        "temp_id": "m1",
                                        "content": "材料正文",
                                        "bbox": [20, 40, 220, 120],
                                    }
                                ],
                                "questions": [
                                    {
                                        "index": 1,
                                        "material_temp_id": "m1",
                                        "bbox": [10, 80, 160, 130],
                                        "stem_bbox": [10, 80, 120, 100],
                                    },
                                    {
                                        "index": 2,
                                        "bbox": [10, 150, 160, 210],
                                    }
                                ],
                                "visuals": [
                                    {
                                        "kind": "chart",
                                        "bbox": [30, 20, 200, 70],
                                    }
                                ],
                            },
                            "normalized_result": {
                                "questions": [
                                    {
                                        "index": 1,
                                        "material_temp_id": "m1",
                                        "bbox": [10, 80, 160, 130],
                                        "stem_bbox": [10, 80, 120, 100],
                                    },
                                    {
                                        "index": 2,
                                        "bbox": [10, 150, 160, 210],
                                    }
                                ],
                                "materials": [
                                    {
                                        "temp_id": "m1",
                                        "content": "材料正文",
                                        "bbox": [20, 40, 220, 180],
                                    }
                                ],
                                "visuals": [
                                    {
                                        "kind": "chart",
                                        "bbox": [30, 20, 200, 70],
                                    }
                                ],
                            },
                            "request_status": "ok",
                            "attempts": 1,
                            "attempt_errors": [],
                            "page_warnings": [],
                            "image_size": {"width": 400, "height": 500},
                            "base64_size": 12,
                        },
                        {
                            "page_num": 2,
                            "raw_result": {"materials": [], "questions": [], "visuals": []},
                            "normalized_result": {"materials": [], "questions": [], "visuals": []},
                            "request_status": "ok",
                            "attempts": 1,
                            "attempt_errors": [],
                            "page_warnings": [],
                            "image_size": {"width": 400, "height": 500},
                            "base64_size": 12,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return {
                "questions": [
                    {
                        "index": 1,
                        "type": "single",
                        "content": "有效题干内容",
                        "option_a": "甲",
                        "option_b": "乙",
                        "page_num": 1,
                        "source_bbox": [10.0, 80.0, 160.0, 130.0],
                        "source_confidence": 0.68,
                        "material_temp_id": "m_1",
                        "parse_warnings": ["backward_material_link_low_confidence"],
                    },
                    {"index": 2, "content": "abc", "page_num": 1},
                ],
                "materials": [
                    {
                        "temp_id": "m_1",
                        "content": "材料正文",
                        "parse_warnings": [],
                    }
                ],
                "stats": {
                    "question_candidates_count": 2,
                    "accepted_questions_count": 2,
                    "rejected_questions_count": 0,
                },
            }

        with TemporaryDirectory() as tmpdir, patch(
            "tools.visual_api_smoke.PDFExtractor",
            FakeSmokeExtractor,
        ), patch(
            "tools.visual_api_smoke.parse_extractor_with_kernel",
            side_effect=fake_kernel_parse,
        ):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            summary = run_visual_api_smoke(
                str(pdf_path),
                page_limit=1,
                output_dir=tmpdir,
            )

            output = Path(tmpdir)
            self.assertTrue((output / "raw_model_response.json").exists())
            self.assertTrue((output / "page_screenshots" / "page_001.png").exists())
            self.assertTrue((output / "page_parse_summary.json").exists())
            self.assertTrue((output / "summary.json").exists())
            self.assertTrue((output / "review_manifest.json").exists())
            self.assertTrue((output / "review_manifest.csv").exists())
            self.assertTrue((output / "rejected_candidates.json").exists())
            self.assertTrue((output / "debug" / "overlays" / "page_001_overlay.png").exists())
            self.assertTrue(any((output / "debug" / "crops").glob("page_001_q001_conf_0.68_crop.png")))
            self.assertTrue(any((output / "debug" / "crops").glob("page_001_material_m_1_conf_0.85_crop.png")))
            lineage = json.loads((output / "debug" / "bbox_lineage.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(lineage), 2)
            question_lineage = next(item for item in lineage if item["linked_question_id"] == 1)
            self.assertIn("raw_bbox", question_lineage)
            self.assertIn("expanded_bbox", question_lineage)
            self.assertIn("clamped_bbox", question_lineage)
            self.assertIn("final_bbox", question_lineage)
            self.assertIn("material_bbox", question_lineage)
            self.assertIn("visual_bbox_list", question_lineage)
            self.assertEqual(question_lineage["next_question_boundary"], 150.0)
            self.assertEqual(question_lineage["crop_context_mode"], "question_with_material")
            self.assertLessEqual(question_lineage["final_bbox"][1], 12)
            self.assertLess(question_lineage["final_bbox"][3], 150)
            self.assertIn("next_question_boundary", question_lineage["clamp_reason"])
            self.assertEqual(question_lineage["linked_visual_count"], 1)
            self.assertIn("backward_material_link_low_confidence", question_lineage["warnings"])
            self.assertEqual(summary["page_limit"], 1)
            self.assertEqual(summary["candidate_counts"]["kernel_question_candidates"], 2)
            self.assertEqual(summary["candidate_counts"]["accepted_questions"], 1)
            self.assertEqual(summary["candidate_counts"]["rejected_candidates"], 1)
            self.assertEqual(summary["rejected_candidates"][0]["reason"], "content_too_short")
            self.assertEqual(summary["pages"][0]["attempts"], 1)
            review_manifest = json.loads((output / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(review_manifest), 1)
            review_record = review_manifest[0]
            self.assertEqual(review_record["question_index"], 1)
            self.assertEqual(review_record["question_id"], "page_001_q001")
            self.assertTrue(review_record["accepted"])
            self.assertEqual(review_record["crop_context_mode"], "question_with_material")
            self.assertEqual(review_record["linked_material_id"], "m_1")
            self.assertEqual(review_record["linked_visual_count"], 1)
            self.assertEqual(review_record["next_question_boundary"], 150.0)
            self.assertFalse(Path(review_record["crop_path"]).is_absolute())
            self.assertFalse(Path(review_record["overlay_path"]).is_absolute())
            self.assertFalse(Path(review_record["material_crop_path"]).is_absolute())
            smoke_summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(smoke_summary["total_questions"], 1)
            self.assertEqual(smoke_summary["accepted_questions"], 1)
            self.assertEqual(smoke_summary["rejected_candidates"], 1)
            self.assertEqual(smoke_summary["questions_with_material"], 1)
            self.assertEqual(smoke_summary["questions_with_visuals"], 1)
            self.assertEqual(len(smoke_summary["suspicious_crops"]), 1)
            self.assertIn("touches_next_question_boundary", smoke_summary["suspicious_crops"][0]["reasons"])

    def test_visual_smoke_runs_discrete_page_window_with_original_page_artifacts(self):
        captured_pages: list[int] = []
        captured_region: list[str] = []

        def fake_kernel_parse(extractor, *, page_limit, debug_dir, retry_failed_pages_only=False):
            debug = Path(debug_dir) / "debug"
            debug.mkdir(parents=True, exist_ok=True)
            for page_index in range(page_limit):
                extractor.get_page_text(page_index)
            captured_region.append(extractor.get_region_screenshot(0, "rect", padding=7))
            captured_pages.extend(extractor.page_indexes)
            (debug / "visual_pages.json").write_text(
                json.dumps(
                    [
                        {
                            "page_num": 1,
                            "raw_result": {
                                "materials": [],
                                "questions": [{"index": 8, "bbox": [10, 40, 160, 90]}],
                                "visuals": [],
                            },
                            "normalized_result": {
                                "materials": [],
                                "questions": [{"index": 8, "bbox": [10, 40, 160, 90]}],
                                "visuals": [],
                            },
                            "request_status": "ok",
                            "attempts": 1,
                            "attempt_errors": [],
                            "page_warnings": [],
                            "image_size": {"width": 400, "height": 500},
                            "base64_size": 12,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return {
                "questions": [
                    {
                        "index": 8,
                        "type": "single",
                        "content": "这是一个有效题干内容",
                        "option_a": "甲",
                        "option_b": "乙",
                        "page_num": 1,
                    }
                ],
                "materials": [],
                "stats": {"question_candidates_count": 1},
            }

        with TemporaryDirectory() as tmpdir, patch(
            "tools.visual_api_smoke.PDFExtractor",
            FakeSmokeExtractor,
        ), patch(
            "tools.visual_api_smoke.parse_extractor_with_kernel",
            side_effect=fake_kernel_parse,
        ):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            summary = run_visual_api_smoke(str(pdf_path), pages="2,3", output_dir=tmpdir)

            output = Path(tmpdir)
            self.assertEqual(captured_pages, [2, 3])
            self.assertEqual(captured_region, ["region-page-2-padding-7"])
            self.assertEqual(summary["page_spec"], "2,3")
            self.assertEqual(summary["page_indexes"], [2, 3])
            self.assertEqual(summary["pages"][0]["page_num"], 3)
            self.assertTrue((output / "page_screenshots" / "page_003.png").exists())
            self.assertTrue((output / "page_screenshots" / "page_004.png").exists())
            self.assertTrue((output / "debug" / "overlays" / "page_003_overlay.png").exists())

    def test_visual_smoke_rejects_full_book_limits(self):
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                run_visual_api_smoke("/tmp/题本篇.pdf", page_limit=225, output_dir=tmpdir)

    def test_visual_smoke_rejects_pages_spec_over_smoke_limit(self):
        with TemporaryDirectory() as tmpdir, patch(
            "tools.visual_api_smoke.PDFExtractor",
            LargeFakeSmokeExtractor,
        ), patch(
            "tools.visual_api_smoke.parse_extractor_with_kernel",
            side_effect=AssertionError("--pages limit was not enforced"),
        ):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            with self.assertRaisesRegex(ValueError, "shrink --pages"):
                run_visual_api_smoke(str(pdf_path), pages="0-225", output_dir=tmpdir)

    def test_visual_cache_miss_calls_api_and_writes_cache(self):
        with TemporaryDirectory() as tmpdir, patch("tools.visual_api_smoke.PDFExtractor", FakeSmokeExtractor), patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value=_visual_result(1, "cache miss content"),
        ) as parse_visual:
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\ncache-miss")
            summary = run_visual_api_smoke(
                str(pdf_path),
                pages="1",
                output_dir=str(Path(tmpdir) / "out"),
                cache_dir=str(Path(tmpdir) / "cache"),
            )

            self.assertEqual(parse_visual.call_count, 1)
            self.assertEqual(summary["cache_hits"], 0)
            self.assertEqual(summary["cache_misses"], 1)
            page_summary = summary["pages"][0]
            self.assertFalse(page_summary["cache_hit"])
            self.assertTrue(Path(page_summary["cache_path"]).exists())

    def test_visual_cache_hit_does_not_call_api(self):
        with TemporaryDirectory() as tmpdir, patch("tools.visual_api_smoke.PDFExtractor", FakeSmokeExtractor):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\ncache-hit")
            cache_dir = Path(tmpdir) / "cache"
            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                return_value=_visual_result(1, "cached content"),
            ):
                run_visual_api_smoke(
                    str(pdf_path),
                    pages="1",
                    output_dir=str(Path(tmpdir) / "first"),
                    cache_dir=str(cache_dir),
                )

            with patch("parser_kernel.adapter.ai_client.parse_page_visual", side_effect=AssertionError("cache miss")):
                summary = run_visual_api_smoke(
                    str(pdf_path),
                    pages="1",
                    output_dir=str(Path(tmpdir) / "second"),
                    cache_dir=str(cache_dir),
                )

            self.assertEqual(summary["cache_hits"], 1)
            self.assertEqual(summary["cache_misses"], 0)
            self.assertTrue(summary["pages"][0]["cache_hit"])

    def test_visual_refresh_cache_overwrites_existing_cache(self):
        with TemporaryDirectory() as tmpdir, patch("tools.visual_api_smoke.PDFExtractor", FakeSmokeExtractor):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nrefresh-cache")
            cache_dir = Path(tmpdir) / "cache"
            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                return_value=_visual_result(1, "old content"),
            ):
                first = run_visual_api_smoke(
                    str(pdf_path),
                    pages="1",
                    output_dir=str(Path(tmpdir) / "first"),
                    cache_dir=str(cache_dir),
                )

            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                return_value=_visual_result(1, "new content"),
            ) as parse_visual:
                refreshed = run_visual_api_smoke(
                    str(pdf_path),
                    pages="1",
                    output_dir=str(Path(tmpdir) / "second"),
                    cache_dir=str(cache_dir),
                    refresh_cache=True,
                )

            self.assertEqual(parse_visual.call_count, 1)
            self.assertEqual(refreshed["cache_hits"], 0)
            self.assertEqual(refreshed["cache_misses"], 1)
            payload = json.loads(Path(first["pages"][0]["cache_path"]).read_text(encoding="utf-8"))
            self.assertIn("new content", json.dumps(payload, ensure_ascii=False))

    def test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest(self):
        calls: list[str] = []

        def first_run(page_b64: str):
            calls.append(page_b64)
            if len(calls) == 2:
                return _timeout_result()
            return _visual_result(len(calls), f"page {len(calls)} ok")

        with TemporaryDirectory() as tmpdir, patch("tools.visual_api_smoke.PDFExtractor", FakeSmokeExtractor):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nretry-failed")
            cache_dir = Path(tmpdir) / "cache"
            with patch("parser_kernel.adapter.ai_client.parse_page_visual", side_effect=first_run):
                first_summary = run_visual_api_smoke(
                    str(pdf_path),
                    pages="0-3",
                    output_dir=str(Path(tmpdir) / "first"),
                    cache_dir=str(cache_dir),
                )

            self.assertEqual(first_summary["failed_pages"], [1])
            calls.clear()
            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                side_effect=lambda page_b64: calls.append(page_b64) or _visual_result(2, "retry ok"),
            ):
                retry_summary = run_visual_api_smoke(
                    str(pdf_path),
                    pages="0-3",
                    output_dir=str(Path(tmpdir) / "first"),
                    cache_dir=str(cache_dir),
                    retry_failed_pages_only=True,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(retry_summary["page_indexes"], [0, 1, 2])
            self.assertEqual(retry_summary["retried_pages"], [1])
            self.assertEqual(retry_summary["cache_hits"], 2)
            self.assertEqual(retry_summary["cache_misses"], 1)
            self.assertEqual(retry_summary["failed_pages"], [])
            review_manifest = json.loads(
                (Path(tmpdir) / "first" / "review_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual([record["page_num"] for record in review_manifest], [1, 2, 3])
            with (Path(tmpdir) / "first" / "review_manifest.csv").open(encoding="utf-8", newline="") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 3)

    def test_corrupt_visual_cache_is_miss_and_overwritten(self):
        with TemporaryDirectory() as tmpdir, patch("tools.visual_api_smoke.PDFExtractor", FakeSmokeExtractor):
            pdf_path = Path(tmpdir) / "题本篇.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\ncorrupt-cache")
            cache_dir = Path(tmpdir) / "cache"
            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                return_value=_visual_result(1, "original cached content"),
            ):
                first = run_visual_api_smoke(
                    str(pdf_path),
                    pages="1",
                    output_dir=str(Path(tmpdir) / "first"),
                    cache_dir=str(cache_dir),
                )

            cache_path = Path(first["pages"][0]["cache_path"])
            cache_path.write_text("{broken", encoding="utf-8")
            with patch(
                "parser_kernel.adapter.ai_client.parse_page_visual",
                return_value=_visual_result(1, "recovered content"),
            ) as parse_visual:
                second = run_visual_api_smoke(
                    str(pdf_path),
                    pages="1",
                    output_dir=str(Path(tmpdir) / "second"),
                    cache_dir=str(cache_dir),
                )

            self.assertEqual(parse_visual.call_count, 1)
            self.assertEqual(second["cache_hits"], 0)
            self.assertEqual(second["cache_misses"], 1)
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertIn("recovered content", json.dumps(payload, ensure_ascii=False))


def _visual_result(index: int, content: str) -> dict:
    return {
        "page_type": "question",
        "warnings": [],
        "materials": [],
        "questions": [
            {
                "index": index,
                "content": content,
                "bbox": [10, 40, 300, 160],
                "stem_bbox": [10, 40, 300, 90],
                "option_a": "甲",
                "option_b": "乙",
                "option_c": "丙",
                "option_d": "丁",
            }
        ],
        "visuals": [],
    }


def _timeout_result() -> dict:
    return {
        "page_type": "unknown",
        "materials": [],
        "questions": [],
        "visuals": [],
        "warnings": ["vision_page_timeout"],
        "raw_model_result": {"error": "vision_page_timeout"},
    }


if __name__ == "__main__":
    unittest.main()
