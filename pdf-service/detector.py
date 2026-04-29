from __future__ import annotations

import re
from typing import Any

from extractor import PDFExtractor


class PDFDetector:
    """Detect broad PDF shape before choosing a parsing strategy."""

    MATERIAL_KEYWORDS = [
        "根据以下",
        "根据以上",
        "阅读以下",
        "下面是",
        "下图",
        "下表",
        "如图所示",
        "如表所示",
        "据此回答",
        "回答第",
    ]
    CHAPTER_KEYWORDS = [
        "第一章",
        "第二章",
        "第三章",
        "第四章",
        "第五章",
        "第六章",
        "第七章",
        "第八章",
        "第九章",
        "第十章",
        "一、",
        "二、",
        "三、",
        "四、",
        "考法一",
        "考法二",
    ]
    TOC_PATTERN = re.compile(r"\.{4,}\s*\d+\s*$", re.MULTILINE)
    OPTION_PATTERN = re.compile(r"[A-D][．.、。]\s*\S")
    QUESTION_NUM_PATTERN = re.compile(r"^\s*\d{1,3}[．.、]\s*\S", re.MULTILINE)
    EXAM_SECTION_PATTERN = re.compile(r"第[一二三四五六七八九十]+部分|注意事项|考试时间")

    def detect(self, extractor: PDFExtractor) -> dict[str, Any]:
        sample_pages = min(10, extractor.total_pages)
        full_sample_text = ""
        image_page_count = 0

        for page_num in range(sample_pages):
            text = extractor.get_page_text(page_num)
            full_sample_text += "\n" + text
            if extractor.get_all_visual_elements(page_num):
                image_page_count += 1

        total_lines = len([line for line in full_sample_text.splitlines() if line.strip()])
        if total_lines == 0:
            return {
                "type": "visual_heavy",
                "confidence": 0.5,
                "stats": {
                    "total_pages": extractor.total_pages,
                    "image_ratio": 1.0 if image_page_count else 0,
                    "toc_ratio": 0,
                    "option_count": 0,
                    "question_count": 0,
                    "chapter_count": 0,
                    "material_count": 0,
                },
            }

        toc_lines = len(self.TOC_PATTERN.findall(full_sample_text))
        option_count = len(self.OPTION_PATTERN.findall(full_sample_text))
        question_count = len(self.QUESTION_NUM_PATTERN.findall(full_sample_text))
        chapter_count = sum(1 for keyword in self.CHAPTER_KEYWORDS if keyword in full_sample_text)
        material_count = sum(1 for keyword in self.MATERIAL_KEYWORDS if keyword in full_sample_text)
        image_ratio = image_page_count / max(sample_pages, 1)
        toc_ratio = toc_lines / total_lines
        exam_section_count = len(self.EXAM_SECTION_PATTERN.findall(full_sample_text))

        pdf_type = "pure_text"
        confidence = 0.5
        if toc_ratio > 0.25:
            pdf_type = "textbook"
            confidence = min(0.9, toc_ratio * 3)
        elif material_count >= 2 or image_ratio > 0.4:
            pdf_type = "visual_heavy"
            confidence = min(0.9, max(material_count / 5, image_ratio))
        elif exam_section_count >= 2 and option_count > 10:
            pdf_type = "exam_paper"
            confidence = 0.75
        elif option_count > max(question_count * 3, 8) and chapter_count < 3:
            pdf_type = "pure_text"
            confidence = 0.8

        return {
            "type": pdf_type,
            "confidence": round(confidence, 2),
            "stats": {
                "total_pages": extractor.total_pages,
                "image_ratio": round(image_ratio, 2),
                "toc_ratio": round(toc_ratio, 2),
                "option_count": option_count,
                "question_count": question_count,
                "chapter_count": chapter_count,
                "material_count": material_count,
                "exam_section_count": exam_section_count,
            },
        }
