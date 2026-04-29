from __future__ import annotations

import logging
import os
from typing import Any

from extractor import PDFExtractor

logger = logging.getLogger(__name__)


class VisualStrategy:
    """Visual-heavy PDF strategy: page screenshot -> VL JSON -> visual attachment."""

    def __init__(self) -> None:
        self.max_visual_elements_per_page = int(os.getenv("MAX_VISUAL_ELEMENTS_PER_PAGE", "3"))

    def parse(self, extractor: PDFExtractor, ai_client_module: Any) -> dict[str, Any]:
        all_questions: list[dict[str, Any]] = []
        all_materials: list[dict[str, Any]] = []
        material_counter = 0

        for page_num in range(extractor.total_pages):
            try:
                page_b64 = extractor.get_page_screenshot(page_num, dpi=150)
                page_result = ai_client_module.parse_page_visual(page_b64)
            except Exception as exc:
                logger.exception("第 %s 页视觉解析失败，已跳过该页: %s", page_num + 1, exc)
                continue

            if page_result.get("page_type") not in {"question", "mixed"}:
                continue

            try:
                visual_elements = extractor.get_all_visual_elements(page_num)[: self.max_visual_elements_per_page]
            except Exception as exc:
                logger.warning("第 %s 页视觉元素提取失败，继续解析文字题目: %s", page_num + 1, exc)
                visual_elements = []
            page_material_map: dict[str, str] = {}

            for material_data in page_result.get("materials", []):
                material_counter += 1
                db_material = {
                    "temp_id": f"page{page_num + 1}_m{material_counter}",
                    "content": material_data.get("content", ""),
                    "images": [],
                }
                if material_data.get("has_visual") and visual_elements:
                    for element in visual_elements:
                        ai_desc = ai_client_module.describe_visual_element(
                            element["base64"],
                            material_data.get("content", "")[:100],
                        )
                        db_material["images"].append(
                            {
                                "base64": element["base64"],
                                "type": element["type"],
                                "ai_desc": ai_desc,
                            }
                        )

                all_materials.append(db_material)
                temp_id = material_data.get("temp_id")
                if temp_id:
                    page_material_map[temp_id] = db_material["temp_id"]

            page_questions = [dict(question) for question in page_result.get("questions", [])]
            shared_visual_material_id = None
            if visual_elements and any(not question.get("material_temp_id") for question in page_questions):
                material_counter += 1
                shared_visual_material_id = f"page{page_num + 1}_m{material_counter}"
                all_materials.append(
                    {
                        "temp_id": shared_visual_material_id,
                        "content": f"第 {page_num + 1} 页图表/图片材料",
                        "images": [
                            {
                                "base64": element["base64"],
                                "type": element["type"],
                                "ai_desc": ai_client_module.describe_visual_element(
                                    element["base64"],
                                    f"第 {page_num + 1} 页图表/图片材料",
                                ),
                            }
                            for element in visual_elements
                        ],
                    }
                )

            for question in page_questions:
                original_material_id = question.get("material_temp_id")
                if original_material_id and original_material_id in page_material_map:
                    question["material_temp_id"] = page_material_map[original_material_id]
                elif shared_visual_material_id:
                    # Avoid duplicating the same large base64 visual on every
                    # question. Store page visuals once as a material and link
                    # affected questions to it, which keeps parse responses and
                    # DB writes small enough to avoid connection resets.
                    question["material_temp_id"] = shared_visual_material_id

                if not question.get("answer"):
                    question["needs_review"] = True

                all_questions.append(question)

        return {"questions": all_questions, "materials": all_materials}
