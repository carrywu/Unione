import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from debug_tools.export_visual_debug import build_layout, load_case, prepare_case_pdf, resolve_pdf_path
from debug_tools.visual_assertions import run_visual_assertions
from models import PageContent, TextBlock
from layout_models import LayoutElement, QuestionCoreBlock, VisualBlock
from block_segmenter import segment_question_cores
from parser_kernel.adapter import parse_extractor_with_kernel
from question_splitter import split_questions
from strategies.markdown_question_strategy import MarkdownQuestionStrategy
from tests.test_scanned_question_book_kernel import FakeScannedQuestionExtractor
from validator import validate_and_clean
from visual_linker import assign_visuals


def make_page(page_num: int, blocks: list[tuple[list[float], str]]) -> PageContent:
    return PageContent(
        page_num=page_num,
        text="\n".join(text for _, text in blocks),
        blocks=[TextBlock(bbox=bbox, text=text) for bbox, text in blocks],
        regions=[],
    )


class PdfReviewFlowRulesTest(unittest.TestCase):
    def test_repeated_header_is_removed_from_cross_page_question(self):
        pages = [
            make_page(
                1,
                [
                    ([0, 10, 1000, 28], "资料分析题库-夸夸刷"),
                    ([0, 120, 1000, 150], "1. 根据材料，下列说法正确的是"),
                    ([0, 170, 1000, 200], "A. 甲"),
                ],
            ),
            make_page(
                2,
                [
                    ([0, 10, 1000, 28], "资料分析题库-夸夸刷"),
                    ([0, 120, 1000, 150], "B. 乙"),
                    ([0, 170, 1000, 200], "C. 丙"),
                    ([0, 220, 1000, 250], "D. 丁"),
                    ([0, 300, 1000, 330], "2. 第二题题干"),
                    ([0, 350, 1000, 380], "A. 甲"),
                    ([0, 400, 1000, 430], "B. 乙"),
                    ([0, 450, 1000, 480], "C. 丙"),
                    ([0, 500, 1000, 530], "D. 丁"),
                ],
            ),
            make_page(
                3,
                [
                    ([0, 10, 1000, 28], "资料分析题库-夸夸刷"),
                    ([0, 120, 1000, 150], "3. 第三题题干"),
                    ([0, 170, 1000, 200], "A. 甲"),
                    ([0, 220, 1000, 250], "B. 乙"),
                    ([0, 270, 1000, 300], "C. 丙"),
                    ([0, 320, 1000, 350], "D. 丁"),
                ],
            ),
            make_page(
                4,
                [
                    ([0, 10, 1000, 28], "资料分析题库-夸夸刷"),
                    ([0, 120, 1000, 150], "4. 第四题题干"),
                    ([0, 170, 1000, 200], "A. 甲"),
                    ([0, 220, 1000, 250], "B. 乙"),
                    ([0, 270, 1000, 300], "C. 丙"),
                    ([0, 320, 1000, 350], "D. 丁"),
                ],
            ),
        ]

        questions = split_questions(pages)

        self.assertEqual(len(questions), 4)
        self.assertNotIn("资料分析题库-夸夸刷", questions[0].text)
        self.assertIn("B. 乙", questions[0].text)

    def test_unlinked_visual_above_question_is_attached_to_nearest_following_question(self):
        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 1,
                        "content": "根据上图，下列说法正确的是",
                        "bbox": [0, 360, 1000, 620],
                        "stem_bbox": [0, 360, 1000, 410],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [
                    {
                        "kind": "chart",
                        "bbox": [120, 80, 880, 320],
                        "caption": "2012~2016 年社会消费品零售总额",
                    }
                ],
            },
        ):
            result = parse_extractor_with_kernel(FakeScannedQuestionExtractor(), debug_dir=tmpdir)

        question = result["questions"][0]
        image_roles = [image["role"] for image in question["images"]]
        self.assertIn("chart", image_roles)
        self.assertEqual(
            [image.get("caption") for image in question["images"] if image["role"] == "chart"],
            ["2012~2016 年社会消费品零售总额"],
        )

    def test_adjacent_table_visuals_are_merged_before_question_attachment(self):
        calls: list[list[float]] = []

        class RecordingExtractor(FakeScannedQuestionExtractor):
            def get_region_screenshot(self, page_num: int, rect, padding: int = 10) -> str:
                calls.append([rect.x0, rect.y0, rect.x1, rect.y1])
                return "fake-region-b64"

            def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
                return {"width": 1000, "height": 1400}

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.ai_client.parse_page_visual",
            return_value={
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [
                    {
                        "index": 4,
                        "content": "根据表格可以推出的是",
                        "bbox": [0, 520, 1000, 780],
                        "stem_bbox": [0, 520, 1000, 570],
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "visuals": [
                    {"kind": "table", "bbox": [120, 80, 880, 260], "caption": "表 1 工业大数据"},
                    {"kind": "table", "bbox": [130, 286, 875, 460], "caption": "表 1 工业大数据续"},
                ],
            },
        ):
            result = parse_extractor_with_kernel(RecordingExtractor(), debug_dir=tmpdir)
            self.assertTrue(Path(tmpdir, "debug", "visual_pages.json").exists())

        table_images = [image for image in result["questions"][0]["images"] if image["role"] == "table"]
        self.assertEqual(len(table_images), 1)
        self.assertEqual(table_images[0]["bbox"], [120.0, 80.0, 880.0, 460.0])
        self.assertEqual(table_images[0]["same_visual_group_id"], "vg_p1_1")

    def test_visual_between_completed_question_and_next_anchor_binds_to_next_question(self):
        elements = [
            LayoutElement("e1", 1, "question_marker", "例1】第一题", [0, 100, 100, 120], None, "例1】第一题", 1),
            LayoutElement("e2", 1, "option", "D. 2027 年", [0, 180, 100, 200], None, "D. 2027 年", 2),
            LayoutElement("e3", 1, "image", None, [0, 220, 100, 320], "images/social.png", "![image](images/social.png)", 3),
            LayoutElement("e4", 1, "caption", "2012~2016 年社会消费品零售总额", [0, 330, 100, 350], None, "2012~2016 年社会消费品零售总额", 4),
            LayoutElement("e5", 1, "question_marker", "例2】社会消费品零售总额首次超过40 万亿元", [0, 370, 100, 390], None, "例2】社会消费品零售总额首次超过40 万亿元", 5),
        ]
        questions = [
            QuestionCoreBlock(
                id="q1",
                index=1,
                source=None,
                page_start=1,
                page_end=1,
                marker_text="例1】第一题",
                stem_text="第一题问可穿戴设备",
                options={"A": "1", "B": "2", "C": "3", "D": "4"},
                element_ids=["e1", "e2", "e3", "e4"],
                bbox_range=[],
                raw_markdown="",
            ),
            QuestionCoreBlock(
                id="q2",
                index=2,
                source=None,
                page_start=1,
                page_end=1,
                marker_text="例2】社会消费品零售总额首次超过40 万亿元",
                stem_text="社会消费品零售总额首次超过40 万亿元",
                options={"A": "1", "B": "2", "C": "3", "D": "4"},
                element_ids=["e5"],
                bbox_range=[],
                raw_markdown="",
            ),
        ]
        visuals = [
            VisualBlock(
                id="v-social",
                page=1,
                kind="image",
                bbox=[0, 220, 100, 320],
                image_path="images/social.png",
                nearby_text_after="2012~2016 年社会消费品零售总额\n例2】社会消费品零售总额首次超过40 万亿元",
            )
        ]

        assignments = assign_visuals(visuals, questions, [], elements)

        self.assertEqual(assignments["questions"]["q1"], [])
        self.assertEqual(assignments["questions"]["q2"], ["v-social"])

    def test_render_fallback_visual_near_extracted_image_is_not_assigned_as_duplicate(self):
        elements = [
            LayoutElement("e1", 1, "question_marker", "例2】社会消费品零售总额", [0, 100, 100, 120], None, "例2】社会消费品零售总额", 1),
            LayoutElement("e2", 1, "image", None, [120, 200, 380, 320], "images/social.png", "![image](images/social.png)", 2),
            LayoutElement("e3", 1, "image", None, [60, 312, 440, 390], "images/fallback.png", "![chart](images/fallback.png)", 3),
        ]
        questions = [
            QuestionCoreBlock(
                id="q2",
                index=2,
                source=None,
                page_start=1,
                page_end=1,
                marker_text="例2】社会消费品零售总额",
                stem_text="社会消费品零售总额首次超过40 万亿元",
                options={"A": "1", "B": "2", "C": "3", "D": "4"},
                element_ids=["e1", "e2", "e3"],
                bbox_range=[],
                raw_markdown="",
            )
        ]
        visuals = [
            VisualBlock("v-social", 1, "image", [120, 200, 380, 320], "images/social.png"),
            VisualBlock(
                "v-fallback",
                1,
                "chart",
                [60, 312, 440, 390],
                "images/fallback.png",
                warnings=["render_cv_fallback_raster"],
            ),
        ]

        assignments = assign_visuals(visuals, questions, [], elements)

        self.assertEqual(assignments["questions"]["q2"], ["v-social"])
        self.assertIn("visual_duplicate_fallback_ignored", visuals[1].warnings)

    def test_question_core_ignores_header_and_post_option_visual_titles(self):
        elements = [
            LayoutElement("e1", 1, "question_marker", "例2】社会消费品零售总额首次超过40 万亿元的年份是：", [0, 100, 100, 120], None, "例2】社会消费品零售总额首次超过40 万亿元的年份是：", 1),
            LayoutElement("e2", 1, "option", "A. 2017 年", [0, 130, 100, 150], None, "A. 2017 年", 2),
            LayoutElement("e3", 1, "text", "1", [0, 160, 100, 180], None, "1", 3),
            LayoutElement("e4", 1, "text", "资料分析题库-夸夸刷", [0, 190, 100, 210], None, "资料分析题库-夸夸刷", 4),
            LayoutElement("e5", 1, "option", "B. 2018 年", [0, 220, 100, 240], None, "B. 2018 年", 5),
            LayoutElement("e6", 1, "option", "C. 2019 年", [0, 250, 100, 270], None, "C. 2019 年", 6),
            LayoutElement("e7", 1, "option", "D. 2020 年", [0, 280, 100, 300], None, "D. 2020 年", 7),
            LayoutElement("e8", 1, "text", "2009~2018 年我国教育经费投入及教育信息化细分行业市场规模", [0, 310, 100, 330], None, "2009~2018 年我国教育经费投入及教育信息化细分行业市场规模", 8),
            LayoutElement("e9", 1, "question_marker", "例3】教育信息化总体市场规模", [0, 340, 100, 360], None, "例3】教育信息化总体市场规模", 9),
        ]

        cores = segment_question_cores(elements, "")

        self.assertEqual(cores[0].options["A"], "2017 年")
        self.assertNotIn("资料分析题库", cores[0].stem_text)
        self.assertNotIn("2009~2018", cores[0].stem_text)

    def test_admin_demo_examples_1_to_4_visual_assignment_regression(self):
        pdf_path = Path("/tmp/admin-demo-question-book.pdf")
        if not pdf_path.exists():
            self.skipTest("/tmp/admin-demo-question-book.pdf is not available")

        with TemporaryDirectory() as tmpdir:
            parsed = MarkdownQuestionStrategy().parse(str(pdf_path), output_dir=tmpdir)

        by_index = {question["index"]: question for question in parsed["questions"]}
        expected_refs = {
            1: ["p1-img1"],
            2: ["p1-img2"],
            3: ["p2-img1"],
            4: ["p2-img2"],
        }
        for index, refs in expected_refs.items():
            self.assertIn(index, by_index)
            self.assertEqual([image["ref"] for image in by_index[index]["images"]], refs)
            self.assertNotIn("资料分析题库", by_index[index]["content"])
            self.assertNotIn("夸夸刷", by_index[index]["content"])

    def test_admin_demo_examples_1_to_10_visual_assignment_and_source_bbox_regression(self):
        case_path = Path(__file__).resolve().parents[1] / "debug_tools" / "cases" / "example_1_10.yml"
        case = load_case(case_path)
        try:
            pdf_path = resolve_pdf_path(case_path, str(case["pdf"]))
        except FileNotFoundError as exc:
            self.skipTest(str(exc))

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "debug"
            output_dir.mkdir()
            working_pdf = prepare_case_pdf(pdf_path=pdf_path, pages=case.get("pages") or [], out_dir=output_dir)
            parsed = MarkdownQuestionStrategy().parse(str(working_pdf), output_dir=str(output_dir))
            layout = build_layout(
                case=case,
                parsed=parsed,
                output_dir=output_dir,
                source_pdf=pdf_path,
                working_pdf=working_pdf,
            )
            assertions = run_visual_assertions(layout, case)

        self.assertTrue(
            assertions["passed"],
            json.dumps(assertions["failures"], ensure_ascii=False, indent=2),
        )

    def test_validator_accepts_options_dict_without_options_missing_warning(self):
        result = validate_and_clean(
            [
                {
                    "index": 1,
                    "type": "single",
                    "content": "根据图表可以推出的是",
                    "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                    "parse_warnings": [],
                }
            ],
            [],
        )

        question = result["questions"][0]
        self.assertEqual(question["option_a"], "甲")
        self.assertNotIn("options_missing", question.get("parse_warnings") or [])


if __name__ == "__main__":
    unittest.main()
