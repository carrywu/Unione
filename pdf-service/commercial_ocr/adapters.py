from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from commercial_ocr.config import get_config_value, get_positive_int
from commercial_ocr.fixtures import fixture_path, provider_result_from_fixture
from commercial_ocr.normalizer import normalize_baidu_page_result
from commercial_ocr.types import NormalizedOCRBlock, ProviderOCRRequest, ProviderOCRResult, ProviderPageResult


logger = logging.getLogger(__name__)

DEFAULT_BAIDU_ENDPOINT = "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu"
DEFAULT_BAIDU_TOKEN_ENDPOINT = "https://aip.baidubce.com/oauth/2.0/token"
DEFAULT_BAIDU_TIMEOUT_MS = 60000


class CommercialOCRProvider(ABC):
    provider_name = "unknown"
    provider_version = "v0"

    @abstractmethod
    def is_available(self) -> tuple[bool, list[str]]:
        raise NotImplementedError

    @abstractmethod
    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        raise NotImplementedError


class FixtureBackedMockProvider(CommercialOCRProvider):
    fixture_name = ""

    def __init__(
        self,
        *,
        provider_name: str | None = None,
        provider_version: str | None = None,
        fixture_name: str | None = None,
        provider_status: str | None = None,
        provider_error: dict[str, Any] | None = None,
        provider_latency_ms: int | None = None,
    ) -> None:
        if provider_name is not None:
            self.provider_name = provider_name
        if provider_version is not None:
            self.provider_version = provider_version
        if fixture_name is not None:
            self.fixture_name = fixture_name
        self._provider_status = provider_status
        self._provider_error = provider_error
        self._provider_latency_ms = provider_latency_ms

    def is_available(self) -> tuple[bool, list[str]]:
        return True, []

    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        started = time.perf_counter()
        effective_fixture_name = (
            get_config_value(
                f"{_provider_config_prefix(self.provider_name)}_fixture_name",
                f"{_provider_env_prefix(self.provider_name)}_FIXTURE_NAME",
            )
            or self.fixture_name
        )
        status = self._provider_status or get_config_value(
            f"{_provider_config_prefix(self.provider_name)}_status",
            f"{_provider_env_prefix(self.provider_name)}_STATUS",
            "ok",
        ) or "ok"
        latency_ms = self._provider_latency_ms
        if latency_ms is None:
            latency_ms = get_positive_int(
                f"{_provider_config_prefix(self.provider_name)}_latency_ms",
                f"{_provider_env_prefix(self.provider_name)}_LATENCY_MS",
                default=8,
            )
        provider_error = self._provider_error or _provider_error_from_env(self.provider_name)
        result = provider_result_from_fixture(
            self.provider_name,
            source_document_id=request.source_document_id,
            task_id=request.task_id,
            fixture_name=effective_fixture_name,
            provider_status=status,
            provider_error=provider_error,
            provider_latency_ms=latency_ms,
        )
        if request.page_numbers:
            if _is_single_fixture_page(result.page_results):
                result.page_results = _rebase_fixture_pages(
                    result.page_results,
                    request.page_numbers[0],
                    self.provider_name,
                )
            else:
                result.page_results = _replicate_fixture_pages(
                    result.page_results,
                    request.page_numbers,
                    self.provider_name,
                )
        if status != "ok":
            result.page_results = [] if status == "error" else result.page_results
            if result.provider_error is None:
                result.provider_error = {
                    "code": f"{self.provider_name}_mock_error",
                    "message": f"mock provider {self.provider_name} forced into {status}",
                }
        result.provider_latency_ms = latency_ms or int((time.perf_counter() - started) * 1000)
        result.raw_response_ref = str(fixture_path(effective_fixture_name))
        return result


class MockCommercialOCRProvider(FixtureBackedMockProvider):
    provider_name = "mock_commercial_ocr"
    provider_version = "fixture-baidu-v1"
    fixture_name = "baidu_paper_cut_edu_single_page_normalized.json"


class MockTencentQuestionSplitProvider(FixtureBackedMockProvider):
    provider_name = "mock_tencent_question_split"
    provider_version = "fixture-tencent-split-v1"
    fixture_name = "tencent_question_split_single_page_normalized.json"


class MockTencentQuestionSplitLayoutProvider(FixtureBackedMockProvider):
    provider_name = "mock_tencent_question_split_layout"
    provider_version = "fixture-tencent-layout-v1"
    fixture_name = "tencent_question_split_layout_single_page_normalized.json"


class BaiduPaperCutEduProvider(CommercialOCRProvider):
    provider_name = "baidu_paper_cut_edu"
    provider_version = "rest2.0-paper-cut-edu"

    def __init__(self) -> None:
        self.endpoint = (
            get_config_value(
                "baidu_ocr_endpoint",
                "BAIDU_OCR_ENDPOINT",
                DEFAULT_BAIDU_ENDPOINT,
            )
            or DEFAULT_BAIDU_ENDPOINT
        )
        self.token_endpoint = DEFAULT_BAIDU_TOKEN_ENDPOINT
        self.timeout_ms = get_positive_int(
            "baidu_ocr_timeout_ms",
            "BAIDU_OCR_TIMEOUT_MS",
            default=DEFAULT_BAIDU_TIMEOUT_MS,
        )
        self.api_key = get_config_value("baidu_api_key", "BAIDU_API_KEY")
        self.secret_key = get_config_value("baidu_secret_key", "BAIDU_SECRET_KEY")
        self.static_access_token = get_config_value(
            "baidu_access_token",
            "BAIDU_ACCESS_TOKEN",
        )

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

            page_result = normalize_baidu_page_result(page_no=page_no, response_json=response_json, provider_name=self.provider_name)
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
            warnings=[warning for page in page_results for warning in page.warnings],
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


def provider_registry() -> dict[str, CommercialOCRProvider]:
    from commercial_ocr.tencent_provider import TencentQuestionSplitLayoutProvider, TencentQuestionSplitProvider

    return {
        "mock_commercial_ocr": MockCommercialOCRProvider(),
        "mock_tencent_question_split": MockTencentQuestionSplitProvider(),
        "mock_tencent_question_split_layout": MockTencentQuestionSplitLayoutProvider(),
        "baidu_paper_cut_edu": BaiduPaperCutEduProvider(),
        "tencent_question_split": TencentQuestionSplitProvider(),
        "tencent_question_split_layout": TencentQuestionSplitLayoutProvider(),
    }


def _write_trace_payload(request: ProviderOCRRequest, payload: dict[str, Any], *, suffix: str) -> str | None:
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


def _replicate_fixture_pages(
    page_results: list[ProviderPageResult],
    page_numbers: list[int],
    provider_name: str,
) -> list[ProviderPageResult]:
    if not page_results:
        return []
    template = page_results[0]
    replicated: list[ProviderPageResult] = []
    for target_page_no in page_numbers:
        blocks = []
        for block in template.blocks:
            blocks.append(
                NormalizedOCRBlock(
                    block_id=f"{provider_name}-{target_page_no}-{block.block_id}",
                    provider_ref=block.provider_ref.replace(":page:1", f":page:{target_page_no}"),
                    page_no=target_page_no,
                    text=block.text,
                    bbox=list(block.bbox),
                    block_type=block.block_type,
                    confidence=block.confidence,
                    reading_order=block.reading_order,
                    parent_block_id=block.parent_block_id,
                    raw=dict(block.raw),
                    warnings=list(block.warnings),
                )
            )
        replicated.append(
            ProviderPageResult(
                page_no=target_page_no,
                blocks=blocks,
                figures=list(template.figures),
                tables=list(template.tables),
                raw=dict(template.raw),
                warnings=list(template.warnings),
            )
        )
    return replicated


def _rebase_fixture_pages(
    page_results: list[ProviderPageResult],
    target_page_no: int,
    provider_name: str,
) -> list[ProviderPageResult]:
    if not page_results:
        return []
    template = page_results[0]
    return [
        ProviderPageResult(
            page_no=target_page_no,
            blocks=[
                NormalizedOCRBlock(
                    block_id=f"{provider_name}-{target_page_no}-{block.block_id}",
                    provider_ref=block.provider_ref.replace(
                        f":page:{block.page_no}",
                        f":page:{target_page_no}",
                    ),
                    page_no=target_page_no,
                    text=block.text,
                    bbox=list(block.bbox),
                    block_type=block.block_type,
                    confidence=block.confidence,
                    reading_order=block.reading_order,
                    parent_block_id=block.parent_block_id,
                    raw=dict(block.raw),
                    warnings=list(block.warnings),
                )
                for block in template.blocks
            ],
            figures=list(template.figures),
            tables=list(template.tables),
            raw=dict(template.raw),
            warnings=list(template.warnings),
        )
    ]


def _is_single_fixture_page(page_results: list[ProviderPageResult]) -> bool:
    if len(page_results) != 1:
        return False
    page_result = page_results[0]
    if not page_result.blocks:
        return True
    page_numbers = {block.page_no for block in page_result.blocks}
    return len(page_numbers) == 1


def _provider_error_from_env(provider_name: str) -> dict[str, Any] | None:
    prefix = _provider_env_prefix(provider_name)
    config_prefix = _provider_config_prefix(provider_name)
    code = get_config_value(
        f"{config_prefix}_error_code",
        f"{prefix}_ERROR_CODE",
    )
    message = get_config_value(
        f"{config_prefix}_error_message",
        f"{prefix}_ERROR_MESSAGE",
    )
    if not code and not message:
        return None
    return {
        "code": code or f"{provider_name}_mock_error",
        "message": message or f"mock provider {provider_name} error",
    }


def _provider_env_prefix(provider_name: str) -> str:
    return provider_name.upper().replace("-", "_")

def _provider_config_prefix(provider_name: str) -> str:
    return provider_name.lower().replace("-", "_")
