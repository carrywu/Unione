from __future__ import annotations

import base64
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from commercial_ocr.types import (
    NormalizedOCRBlock,
    ProviderOCRRequest,
    ProviderOCRResult,
    ProviderPageResult,
)


logger = logging.getLogger(__name__)

DEFAULT_BAIDU_ENDPOINT = "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu"
DEFAULT_BAIDU_TOKEN_ENDPOINT = "https://aip.baidubce.com/oauth/2.0/token"
DEFAULT_BAIDU_TIMEOUT_MS = 30000


class CommercialOCRProvider(ABC):
    provider_name = "unknown"
    provider_version = "v0"

    @abstractmethod
    def is_available(self) -> tuple[bool, list[str]]:
        raise NotImplementedError

    @abstractmethod
    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        raise NotImplementedError


class MockCommercialOCRProvider(CommercialOCRProvider):
    provider_name = "mock_commercial_ocr"
    provider_version = "mock-v1"

    def is_available(self) -> tuple[bool, list[str]]:
        return True, []

    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        started = time.perf_counter()
        page_results: list[ProviderPageResult] = []
        for page_no in request.page_numbers:
            text = str(request.extractor.get_page_text(page_no - 1) or "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                lines = [f"Mock OCR page {page_no}"]
            blocks = [
                NormalizedOCRBlock(
                    block_id=f"mock-{page_no}-{index}",
                    provider_ref=f"mock:page:{page_no}",
                    page_no=page_no,
                    text=line,
                    bbox=[0.0, float(index * 16), 1000.0, float(index * 16 + 12)],
                    block_type=_guess_mock_block_type(line),
                    confidence=0.99,
                    reading_order=index,
                    raw={"source": "page_text"},
                )
                for index, line in enumerate(lines, start=1)
            ]
            page_results.append(
                ProviderPageResult(
                    page_no=page_no,
                    blocks=blocks,
                    raw={"line_count": len(lines), "provider": self.provider_name},
                )
            )
        return ProviderOCRResult(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            source_document_id=request.source_document_id,
            task_id=request.task_id,
            page_results=page_results,
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
            provider_status="ok",
        )


class TencentQuestionSplitProvider(CommercialOCRProvider):
    provider_name = "tencent_question_split"
    provider_version = "stub-v1"

    def is_available(self) -> tuple[bool, list[str]]:
        secret_id = str(os.getenv("TENCENT_SECRET_ID") or "").strip()
        secret_key = str(os.getenv("TENCENT_SECRET_KEY") or "").strip()
        if not secret_id or not secret_key:
            return False, ["missing_tencent_secret_id_or_key", "provider_stub_not_implemented"]
        return False, ["provider_stub_not_implemented"]

    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        return ProviderOCRResult(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            source_document_id=request.source_document_id,
            task_id=request.task_id,
            provider_status="error",
            provider_error={"code": "provider_stub_not_implemented", "message": "Tencent adapter is a stub in M1."},
            warnings=["provider_stub_not_implemented"],
        )


class BaiduPaperCutEduProvider(CommercialOCRProvider):
    provider_name = "baidu_paper_cut_edu"
    provider_version = "rest2.0-paper-cut-edu"

    def __init__(self) -> None:
        self.endpoint = str(os.getenv("BAIDU_OCR_ENDPOINT") or DEFAULT_BAIDU_ENDPOINT).strip()
        self.token_endpoint = DEFAULT_BAIDU_TOKEN_ENDPOINT
        self.timeout_ms = _positive_int(os.getenv("BAIDU_OCR_TIMEOUT_MS"), DEFAULT_BAIDU_TIMEOUT_MS)
        self.api_key = str(os.getenv("BAIDU_API_KEY") or "").strip()
        self.secret_key = str(os.getenv("BAIDU_SECRET_KEY") or "").strip()
        self.static_access_token = str(os.getenv("BAIDU_ACCESS_TOKEN") or "").strip()

    def is_available(self) -> tuple[bool, list[str]]:
        if self.static_access_token:
            return True, []
        missing: list[str] = []
        if not self.api_key:
            missing.append("missing_baidu_api_key")
        if not self.secret_key:
            missing.append("missing_baidu_secret_key")
        return not missing, missing

    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        started = time.perf_counter()
        access_token = self._resolve_access_token()
        if not access_token:
            return ProviderOCRResult(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                source_document_id=request.source_document_id,
                task_id=request.task_id,
                provider_status="error",
                provider_error={"code": "access_token_unavailable", "message": "No Baidu access token is available."},
                warnings=["missing_baidu_access_token"],
            )

        page_results: list[ProviderPageResult] = []
        trace_payload: dict[str, Any] = {
            "provider": self.provider_name,
            "provider_version": self.provider_version,
            "endpoint": self.endpoint,
            "token_endpoint": self.token_endpoint,
            "pages": [],
        }
        for page_no in request.page_numbers:
            page_b64 = request.extractor.get_page_screenshot(page_no - 1, dpi=150, max_side=1800)
            payload = {
                "image": page_b64,
                "language_type": "CHN_ENG",
                "detect_direction": "false",
                "words_type": "handprint_mix",
                "splice_text": "false",
                "enhance": "false",
                "only_split": "false",
            }
            page_started = time.perf_counter()
            try:
                response_json = self._post_page(payload, access_token=access_token)
            except Exception as exc:  # pragma: no cover - exercised by tests via patching
                logger.warning(
                    "Commercial OCR provider=%s status=error page=%s task_id=%s reason=%s",
                    self.provider_name,
                    page_no,
                    request.task_id,
                    exc,
                )
                trace_payload["pages"].append(
                    {
                        "page_no": page_no,
                        "status": "error",
                        "latency_ms": int((time.perf_counter() - page_started) * 1000),
                        "error": str(exc),
                    }
                )
                return ProviderOCRResult(
                    provider_name=self.provider_name,
                    provider_version=self.provider_version,
                    source_document_id=request.source_document_id,
                    task_id=request.task_id,
                    raw_response_ref=_write_trace_payload(request, trace_payload, suffix="failure"),
                    provider_latency_ms=int((time.perf_counter() - started) * 1000),
                    provider_status="error",
                    provider_error={"code": "http_request_failed", "message": str(exc), "page_no": page_no},
                    warnings=["provider_http_error"],
                )

            error_code = response_json.get("error_code")
            if error_code:
                trace_payload["pages"].append(
                    {
                        "page_no": page_no,
                        "status": "error",
                        "latency_ms": int((time.perf_counter() - page_started) * 1000),
                        "response": response_json,
                    }
                )
                return ProviderOCRResult(
                    provider_name=self.provider_name,
                    provider_version=self.provider_version,
                    source_document_id=request.source_document_id,
                    task_id=request.task_id,
                    raw_response_ref=_write_trace_payload(request, trace_payload, suffix="failure"),
                    provider_latency_ms=int((time.perf_counter() - started) * 1000),
                    provider_status="error",
                    provider_error={
                        "code": str(error_code),
                        "message": str(response_json.get("error_msg") or "provider_error"),
                        "page_no": page_no,
                    },
                    warnings=["provider_error_code_returned"],
                )

            page_result = self._normalize_page_result(page_no=page_no, response_json=response_json)
            page_results.append(page_result)
            trace_payload["pages"].append(
                {
                    "page_no": page_no,
                    "status": "ok",
                    "latency_ms": int((time.perf_counter() - page_started) * 1000),
                    "response": response_json,
                }
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Commercial OCR provider=%s status=ok pages=%s latency_ms=%s task_id=%s",
            self.provider_name,
            len(request.page_numbers),
            elapsed_ms,
            request.task_id,
        )
        return ProviderOCRResult(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            source_document_id=request.source_document_id,
            task_id=request.task_id,
            page_results=page_results,
            raw_response_ref=_write_trace_payload(request, trace_payload, suffix="success"),
            provider_latency_ms=elapsed_ms,
            provider_status="ok",
        )

    def _resolve_access_token(self) -> str | None:
        if self.static_access_token:
            return self.static_access_token
        if not self.api_key or not self.secret_key:
            return None
        with httpx.Client(timeout=self.timeout_ms / 1000.0, trust_env=False) as client:
            response = client.post(
                self.token_endpoint,
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.secret_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
        return str(payload.get("access_token") or "").strip() or None

    def _post_page(self, payload: dict[str, str], *, access_token: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout_ms / 1000.0, trust_env=False) as client:
            response = client.post(
                self.endpoint,
                params={"access_token": access_token},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data=payload,
            )
            response.raise_for_status()
            return response.json()

    def _normalize_page_result(self, *, page_no: int, response_json: dict[str, Any]) -> ProviderPageResult:
        blocks: list[NormalizedOCRBlock] = []
        figures: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        reading_order = 1
        for question_index, item in enumerate(response_json.get("qus_result") or [], start=1):
            question_ref = str(item.get("question_id") or item.get("qus_id") or question_index)
            question_bbox = _coerce_bbox(item.get("qus_location"))
            confidence = _safe_float(item.get("qus_probability") or item.get("probability"))
            element_items = item.get("qus_element") or []
            if isinstance(element_items, list) and element_items:
                for element_index, element in enumerate(element_items, start=1):
                    normalized_blocks = self._normalize_question_element(
                        page_no=page_no,
                        question_ref=question_ref,
                        element=element,
                        fallback_bbox=question_bbox,
                        fallback_confidence=confidence,
                        reading_order_start=reading_order,
                    )
                    blocks.extend(normalized_blocks)
                    reading_order += max(1, len(normalized_blocks))
            else:
                reading_order = _append_question_summary_blocks(
                    page_no=page_no,
                    question_ref=question_ref,
                    item=item,
                    blocks=blocks,
                    fallback_bbox=question_bbox,
                    fallback_confidence=confidence,
                    reading_order=reading_order,
                )

            for page_figure in item.get("qus_figure") or []:
                figure_bbox = _coerce_bbox(page_figure)
                if not figure_bbox:
                    continue
                figure_block = NormalizedOCRBlock(
                    block_id=f"baidu-{page_no}-{question_ref}-figure-{len(figures) + 1}",
                    provider_ref=f"baidu:question:{question_ref}",
                    page_no=page_no,
                    text=str(item.get("figure_caption") or ""),
                    bbox=figure_bbox,
                    block_type="figure",
                    confidence=confidence,
                    reading_order=reading_order,
                    raw={"kind": "qus_figure", "question_ref": question_ref},
                )
                reading_order += 1
                blocks.append(figure_block)
                figures.append({"bbox": figure_bbox, "question_ref": question_ref})

        return ProviderPageResult(
            page_no=page_no,
            blocks=_sorted_blocks(blocks),
            figures=figures,
            tables=tables,
            raw=response_json,
            warnings=_warnings_from_baidu_response(response_json),
        )

    def _normalize_question_element(
        self,
        *,
        page_no: int,
        question_ref: str,
        element: dict[str, Any],
        fallback_bbox: list[float],
        fallback_confidence: float | None,
        reading_order_start: int,
    ) -> list[NormalizedOCRBlock]:
        block_type = _baidu_elem_type_to_block_type(element.get("type") or element.get("elem_type"))
        words = element.get("elem_word") or element.get("words") or []
        blocks: list[NormalizedOCRBlock] = []
        if isinstance(words, list) and words:
            reading_order = reading_order_start
            for word_index, word in enumerate(words, start=1):
                text = str(word.get("word") or word.get("text") or "").strip()
                if not text:
                    continue
                blocks.append(
                    NormalizedOCRBlock(
                        block_id=f"baidu-{page_no}-{question_ref}-{block_type}-{word_index}",
                        provider_ref=f"baidu:question:{question_ref}",
                        page_no=page_no,
                        text=text,
                        bbox=_coerce_bbox(word.get("word_location") or word.get("location")) or list(fallback_bbox),
                        block_type=block_type,
                        confidence=_safe_float(element.get("elem_probability") or element.get("probability"))
                        or fallback_confidence,
                        reading_order=reading_order,
                        raw={"element": element, "word": word},
                        warnings=[] if _coerce_bbox(word.get("word_location") or word.get("location")) else ["bbox_missing"],
                    )
                )
                reading_order += 1
            return blocks

        text_candidates = []
        elem_text = element.get("elem_text")
        if isinstance(elem_text, dict):
            for key, value in elem_text.items():
                if isinstance(value, str) and value.strip():
                    text_candidates.append((key, value.strip()))
        elif isinstance(elem_text, str) and elem_text.strip():
            text_candidates.append(("elem_text", elem_text.strip()))

        reading_order = reading_order_start
        for key, text in text_candidates:
            blocks.append(
                NormalizedOCRBlock(
                    block_id=f"baidu-{page_no}-{question_ref}-{block_type}-{key}",
                    provider_ref=f"baidu:question:{question_ref}",
                    page_no=page_no,
                    text=text,
                    bbox=_coerce_bbox(element.get("elem_location") or element.get("location")) or list(fallback_bbox),
                    block_type=_baidu_text_key_override(key, default=block_type),
                    confidence=_safe_float(element.get("elem_probability") or element.get("probability"))
                    or fallback_confidence,
                    reading_order=reading_order,
                    raw={"element": element},
                    warnings=[] if _coerce_bbox(element.get("elem_location") or element.get("location")) else ["bbox_missing"],
                )
            )
            reading_order += 1
        return blocks


def provider_registry() -> dict[str, CommercialOCRProvider]:
    return {
        "mock_commercial_ocr": MockCommercialOCRProvider(),
        "baidu_paper_cut_edu": BaiduPaperCutEduProvider(),
        "tencent_question_split": TencentQuestionSplitProvider(),
    }


def _write_trace_payload(
    request: ProviderOCRRequest,
    payload: dict[str, Any],
    *,
    suffix: str,
) -> str | None:
    trace_root = _trace_root(request)
    trace_root.mkdir(parents=True, exist_ok=True)
    target = trace_root / f"{request.task_id}-{suffix}.json"
    if not request.trace_enabled:
        payload = {
            "provider": payload.get("provider"),
            "provider_version": payload.get("provider_version"),
            "endpoint": payload.get("endpoint"),
            "pages": [
                {
                    "page_no": page.get("page_no"),
                    "status": page.get("status"),
                    "latency_ms": page.get("latency_ms"),
                }
                for page in payload.get("pages") or []
            ],
        }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def _trace_root(request: ProviderOCRRequest) -> Path:
    if request.debug_dir:
        return Path(request.debug_dir) / "debug" / "commercial_ocr"
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "debug" / "provider-trace" / request.source_document_id


def _guess_mock_block_type(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("a.") or lowered.startswith("b.") or lowered.startswith("c.") or lowered.startswith("d."):
        return "option"
    if lowered.startswith("答案") or lowered.startswith("answer"):
        return "answer"
    if lowered.startswith("解析") or lowered.startswith("analysis"):
        return "analysis"
    if any(token in text for token in ("根据以下资料", "回答", "材料")):
        return "material_intro"
    if text[:1].isdigit():
        return "question_no"
    return "text"


def _baidu_elem_type_to_block_type(value: Any) -> str:
    mapping = {
        0: "stem",
        1: "material_intro",
        2: "answer",
        3: "option",
        4: "figure",
        5: "analysis",
    }
    try:
        key = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return mapping.get(key, "unknown")


def _baidu_text_key_override(key: str, *, default: str) -> str:
    return {
        "stem_text": "stem",
        "subqus_text": "material_intro",
        "option_text": "option",
        "answer_text": "answer",
        "interpretation_text": "analysis",
    }.get(key, default)


def _append_question_summary_blocks(
    *,
    page_no: int,
    question_ref: str,
    item: dict[str, Any],
    blocks: list[NormalizedOCRBlock],
    fallback_bbox: list[float],
    fallback_confidence: float | None,
    reading_order: int,
) -> int:
    key_order = [
        ("stem_text", "stem"),
        ("subqus_text", "material_intro"),
        ("option_text", "option"),
        ("answer_text", "answer"),
        ("interpretation_text", "analysis"),
    ]
    for key, block_type in key_order:
        text = str(item.get(key) or "").strip()
        if not text:
            continue
        blocks.append(
            NormalizedOCRBlock(
                block_id=f"baidu-{page_no}-{question_ref}-{key}",
                provider_ref=f"baidu:question:{question_ref}",
                page_no=page_no,
                text=text,
                bbox=list(fallback_bbox),
                block_type=block_type,
                confidence=fallback_confidence,
                reading_order=reading_order,
                raw={"question": item},
                warnings=[] if fallback_bbox else ["bbox_missing"],
            )
        )
        reading_order += 1
    return reading_order


def _sorted_blocks(blocks: list[NormalizedOCRBlock]) -> list[NormalizedOCRBlock]:
    return sorted(blocks, key=lambda block: (block.page_no, block.reading_order, block.bbox[1] if len(block.bbox) >= 2 else 0.0))


def _warnings_from_baidu_response(payload: dict[str, Any]) -> list[str]:
    warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
    if payload.get("log_id") is None:
        warnings.append("baidu_log_id_missing")
    return list(dict.fromkeys(warnings))


def _coerce_bbox(value: Any) -> list[float]:
    if isinstance(value, dict):
        points = value.get("point") or value.get("points")
        if isinstance(points, list):
            return _coerce_bbox(points)
        if all(key in value for key in ("left", "top", "width", "height")):
            left = _safe_float(value.get("left"))
            top = _safe_float(value.get("top"))
            width = _safe_float(value.get("width"))
            height = _safe_float(value.get("height"))
            if None not in {left, top, width, height}:
                return [left, top, left + width, top + height]
    if isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        return [float(item) for item in value]
    if isinstance(value, list) and value:
        points: list[tuple[float, float]] = []
        for item in value:
            if isinstance(item, dict):
                x = _safe_float(item.get("x"))
                y = _safe_float(item.get("y"))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                x = _safe_float(item[0])
                y = _safe_float(item[1])
            else:
                continue
            if x is None or y is None:
                continue
            points.append((x, y))
        if points:
            xs = [item[0] for item in points]
            ys = [item[1] for item in points]
            return [min(xs), min(ys), max(xs), max(ys)]
    return []


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
