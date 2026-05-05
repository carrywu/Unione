from __future__ import annotations

import base64
import io
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


LOCAL_OCR_PROVIDER = "tesseract_local_ocr"
DEFAULT_OCR_DPI = 170
DEFAULT_OCR_MAX_SIDE = 1800
DEFAULT_OCR_LANG = "chi_sim+eng"
DEFAULT_OCR_PSM = 6
QUESTION_START_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、,:：)]\s*(.*)$")
OPTION_RE = re.compile(r"^\s*([A-H])\s*[.．、,:：)]\s*(.*)$")
RANGE_PATTERNS = [
    re.compile(r"(根据以下资料|根据所给资料|根据所给材料|阅读以下材料|请回答)[^0-9]{0,12}(\d{1,3})\s*[-~—一至到]+\s*(\d{1,3})\s*题"),
    re.compile(r"(根据以下资料|根据所给资料|根据所给材料|阅读以下材料)[^0-9]{0,20}回答\s*(\d{1,3})\s*[-~—一至到]+\s*(\d{1,3})\s*题"),
]


def normalize_local_ocr_text(text: str) -> str:
    normalized = (
        str(text or "")
        .replace("\u3000", " ")
        .replace("～", "~")
        .replace("—", "-")
        .replace("—", "-")
        .replace("（", "(")
        .replace("）", ")")
    )
    lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_question_range(text: str) -> list[int]:
    normalized = normalize_local_ocr_text(text)
    for pattern in RANGE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        start = int(match.group(2))
        end = int(match.group(3))
        return [start, end] if start <= end else [end, start]
    return []


def has_material_range_signal(text: str) -> bool:
    return bool(extract_question_range(text))


def local_ocr_page_text(
    *,
    extractor: Any,
    page_no: int,
    dpi: int = DEFAULT_OCR_DPI,
    max_side: int = DEFAULT_OCR_MAX_SIDE,
    lang: str = DEFAULT_OCR_LANG,
    psm: int = DEFAULT_OCR_PSM,
) -> str:
    image_b64 = extractor.get_page_screenshot(page_no - 1, dpi=dpi, max_side=max_side)
    image_bytes = base64.b64decode(image_b64)
    with tempfile.TemporaryDirectory(prefix="local-data-ocr-") as tmpdir:
        image_path = Path(tmpdir) / f"page-{page_no}.png"
        outbase = Path(tmpdir) / f"page-{page_no}"
        image_path.write_bytes(image_bytes)
        subprocess.run(
            [
                "tesseract",
                str(image_path),
                str(outbase),
                "-l",
                lang,
                "--psm",
                str(psm),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        text = outbase.with_suffix(".txt").read_text(encoding="utf-8", errors="ignore")
    return normalize_local_ocr_text(text)


def stitched_page_image_b64(
    *,
    extractor: Any,
    page_numbers: list[int],
    dpi: int = DEFAULT_OCR_DPI,
    max_side: int = DEFAULT_OCR_MAX_SIDE,
) -> str:
    images: list[Image.Image] = []
    for page_no in page_numbers:
        image_b64 = extractor.get_page_screenshot(page_no - 1, dpi=dpi, max_side=max_side)
        images.append(Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB"))
    width = max(image.width for image in images)
    height = sum(image.height for image in images)
    canvas = Image.new("RGB", (width, height), color=(255, 255, 255))
    offset = 0
    for image in images:
        canvas.paste(image, (0, offset))
        offset += image.height
    with io.BytesIO() as buffer:
        canvas.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")


def build_local_group_from_start_page(
    *,
    extractor: Any,
    start_page_no: int,
    max_page_span: int = 3,
) -> dict[str, Any] | None:
    first_page_text = local_ocr_page_text(extractor=extractor, page_no=start_page_no)
    question_range = extract_question_range(first_page_text)
    if not question_range:
        return None
    range_start, range_end = question_range
    page_texts: list[dict[str, Any]] = []
    for page_no in range(start_page_no, min(extractor.total_pages, start_page_no + max_page_span - 1) + 1):
        page_texts.append({"page_no": page_no, "text": local_ocr_page_text(extractor=extractor, page_no=page_no)})

    started = False
    material_lines: list[str] = []
    current_question: dict[str, Any] | None = None
    questions: dict[int, dict[str, Any]] = {}
    last_question_page = start_page_no
    stop = False

    for page in page_texts:
        page_no = int(page["page_no"])
        for raw_line in str(page["text"]).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_range = extract_question_range(line)
            if not started:
                if line_range == question_range:
                    started = True
                continue
            if line_range and line_range != question_range and questions:
                stop = True
                break
            question_match = QUESTION_START_RE.match(line)
            if question_match:
                question_no = int(question_match.group(1))
                if range_start <= question_no <= range_end:
                    current_question = questions.setdefault(
                        question_no,
                        {
                            "question_no": question_no,
                            "stem_lines": [],
                            "options": {},
                            "_last_option": None,
                            "source_page_span": [page_no, page_no],
                        },
                    )
                    current_question["source_page_span"][1] = page_no
                    stem_suffix = question_match.group(2).strip()
                    if stem_suffix:
                        current_question["stem_lines"].append(stem_suffix)
                    last_question_page = page_no
                    continue
                if questions:
                    stop = True
                    break

            if current_question is None:
                material_lines.append(line)
                continue

            option_match = OPTION_RE.match(line)
            if option_match:
                option_key = option_match.group(1)
                option_text = option_match.group(2).strip()
                current_question["options"][option_key] = option_text
                current_question["_last_option"] = option_key
                current_question["source_page_span"][1] = page_no
                continue

            last_option = current_question.get("_last_option")
            if last_option:
                current_question["options"][last_option] = (
                    f"{current_question['options'][last_option]} {line}".strip()
                )
            else:
                current_question["stem_lines"].append(line)
            current_question["source_page_span"][1] = page_no
        if stop:
            break
        if questions and max(questions) >= range_end:
            # The last question in range has been seen; the next page belongs to the next group more often than not.
            break

    ordered_questions: list[dict[str, Any]] = []
    for question_no in range(range_start, range_end + 1):
        payload = questions.get(question_no)
        if payload is None:
            continue
        ordered_questions.append(
            {
                "question_no": question_no,
                "local_stem": " ".join(payload["stem_lines"]).strip(),
                "full_stem": " ".join(payload["stem_lines"]).strip(),
                "options": dict(payload["options"]),
                "ocr_answer_candidate": None,
                "ocr_analysis_candidate": None,
                "source_page_span": list(payload["source_page_span"]),
            }
        )

    if not ordered_questions:
        return None

    source_pages = list(range(start_page_no, last_question_page + 1))
    warnings: list[str] = []
    missing_questions = [question_no for question_no in range(range_start, range_end + 1) if question_no not in questions]
    if missing_questions:
        warnings.append(f"local_ocr_missing_questions:{','.join(str(item) for item in missing_questions)}")

    return {
        "ocr_provider": LOCAL_OCR_PROVIDER,
        "page_no": start_page_no,
        "question_range": [range_start, range_end],
        "source_page_span": [source_pages[0], source_pages[-1]],
        "source_pages": source_pages,
        "shared_stem": f"根据所给材料，回答{range_start}-{range_end}题",
        "material_text": "\n".join(material_lines).strip(),
        "questions": ordered_questions,
        "warnings": warnings,
    }
