from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from block_segmenter import build_exercise_blocks, segment_question_cores, segment_shared_materials
from debug_writer import write_debug_bundle
from layout_extractor import extract_layout_to_markdown
from markdown_extractor import write_markdown_debug
from validators.question_group_validator import validate_parse_result
from visual_linker import assign_visuals


class MarkdownQuestionStrategy:
    """Layout/Markdown-first PDF question parser.

    This strategy deliberately separates question core extraction from visual
    ownership. Visuals are assigned after bidirectional scoring so charts before
    or after stems are handled consistently.
    """

    def parse(self, pdf_path: str, output_dir: str | None = None, ai_config: dict[str, str] | None = None) -> dict[str, Any]:
        output_dir = output_dir or tempfile.mkdtemp(prefix="pdf-md-")
        payload = extract_layout_to_markdown(pdf_path, output_dir)
        question_cores = segment_question_cores(payload["elements"], payload["markdown"])
        materials = segment_shared_materials(payload["elements"], question_cores)
        assignments = assign_visuals(payload["visuals"], question_cores, materials, payload["elements"])
        exercise_blocks = build_exercise_blocks(question_cores, materials, assignments["questions"])
        material_payloads = self._material_payloads(materials, payload["visuals"], output_dir)
        question_payloads = self._question_payloads(exercise_blocks, materials, payload["visuals"], output_dir)
        material_payloads, question_payloads, validation_warnings = validate_parse_result(
            material_payloads,
            question_payloads,
            payload["visuals"],
        )
        write_markdown_debug(payload, output_dir)
        write_debug_bundle(
            output_dir,
            question_cores=question_cores,
            materials=materials,
            exercise_blocks=exercise_blocks,
            questions=question_payloads,
            visuals=payload["visuals"],
            warnings={
                "assignments": assignments["warnings"],
                "validation": validation_warnings,
            },
            ai_chunks=[],
        )
        return {
            "questions": question_payloads,
            "materials": material_payloads,
            "stats": {
                "debug_dir": output_dir,
                "extractor": payload.get("extractor") or "unknown",
                "pages_count": _count_pages(payload["elements"]),
                "page_elements_count": len(payload["elements"]),
                "question_candidates_count": len(exercise_blocks),
                "accepted_questions_count": len(question_payloads),
                "rejected_questions_count": max(0, len(exercise_blocks) - len(question_payloads)),
                "materials_count": len(material_payloads),
                "visuals_count": len(payload["visuals"]),
                "with_images": sum(1 for question in question_payloads if question.get("images")),
            },
        }

    def _question_payloads(self, exercises, materials, visuals, output_dir: str) -> list[dict[str, Any]]:
        visual_by_id = {visual.id: visual for visual in visuals}
        result: list[dict[str, Any]] = []
        for exercise in exercises:
            core = exercise.question_core
            visual_images = [
                self._image_payload(visual_by_id[visual_id], output_dir, "question_material")
                for visual_id in exercise.visual_ids
                if visual_id in visual_by_id
            ]
            warnings = list(exercise.warnings)
            for visual in visual_images:
                if visual.get("assignment_confidence", 1) < 0.65:
                    warnings.append("visual_assignment_low_confidence")
            result.append(
                {
                    "index": core.index,
                    "index_num": core.index,
                    "type": "single",
                    "content": core.stem_text,
                    "options": core.options,
                    "answer": None,
                    "analysis": None,
                    "images": visual_images,
                    "material_id": exercise.material_id,
                    "material_temp_id": exercise.material_id,
                    "page_num": exercise.page_range[0],
                    "page_range": list(exercise.page_range),
                    "source_page_start": exercise.page_range[0],
                    "source_page_end": exercise.page_range[1],
                    "source_bbox": exercise.source_bbox,
                    "source_anchor_text": exercise.source_anchor_text,
                    "source_confidence": exercise.parse_confidence,
                    "image_refs": exercise.visual_ids,
                    "source": core.source,
                    "parse_source": "markdown_question_strategy",
                    "raw_text": exercise.raw_markdown[:12000],
                    "parse_confidence": exercise.parse_confidence,
                    "confidence": exercise.parse_confidence,
                    "needs_review": bool(warnings or exercise.parse_confidence < 0.75),
                    "parse_warnings": sorted(set(warnings)),
                }
            )
        return result

    def _material_payloads(self, materials, visuals, output_dir: str) -> list[dict[str, Any]]:
        visual_by_id = {visual.id: visual for visual in visuals}
        result: list[dict[str, Any]] = []
        for material in materials:
            images = [
                self._image_payload(visual_by_id[visual_id], output_dir, "shared_material")
                for visual_id in material.visual_ids
                if visual_id in visual_by_id
            ]
            result.append(
                {
                    "temp_id": material.id,
                    "id": material.id,
                    "content": material.content,
                    "images": images,
                    "page_start": material.page_start,
                    "page_end": material.page_end,
                    "page_range": [material.page_start, material.page_end],
                    "image_refs": material.visual_ids,
                    "raw_text": material.raw_markdown[:12000],
                    "parse_warnings": material.warnings,
                }
            )
        return result

    def _image_payload(self, visual, output_dir: str, role: str) -> dict[str, Any]:
        image_path = Path(output_dir) / visual.image_path
        encoded = ""
        if image_path.exists():
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return {
            "ref": visual.id,
            "base64": encoded,
            "url": visual.image_path,
            "caption": visual.caption,
            "page": visual.page,
            "role": role,
            "assignment_confidence": visual.assignment_confidence,
        }


def _count_pages(elements) -> int:
    pages = {getattr(element, "page", None) or getattr(element, "page_num", None) for element in elements}
    pages.discard(None)
    return len(pages)
