from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from commercial_ocr.normalizer import normalize_tencent_question_split_response
from commercial_ocr.types import ProviderOCRRequest, ProviderOCRResult
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import models, ocr_client

from commercial_ocr.adapters import CommercialOCRProvider


logger = logging.getLogger(__name__)

DEFAULT_TENCENT_ENDPOINT = "https://ocr.tencentcloudapi.com"
DEFAULT_TENCENT_VERSION = "2018-11-19"
DEFAULT_TENCENT_TIMEOUT_MS = 60000


class TencentQuestionSplitProvider(CommercialOCRProvider):
    provider_name = "tencent_question_split"
    provider_version = f"{DEFAULT_TENCENT_VERSION}:QuestionSplitOCR"
    action_name = "QuestionSplitOCR"
    layout_only = False

    def __init__(self) -> None:
        self.secret_id = str(os.getenv("TENCENT_SECRET_ID") or "").strip()
        self.secret_key = str(os.getenv("TENCENT_SECRET_KEY") or "").strip()
        self.region = str(os.getenv("TENCENT_REGION") or "ap-guangzhou").strip() or "ap-guangzhou"
        self.endpoint = str(os.getenv("TENCENT_OCR_ENDPOINT") or DEFAULT_TENCENT_ENDPOINT).strip() or DEFAULT_TENCENT_ENDPOINT
        self.version = str(os.getenv("TENCENT_OCR_VERSION") or DEFAULT_TENCENT_VERSION).strip() or DEFAULT_TENCENT_VERSION
        self.timeout_ms = _positive_int(os.getenv("TENCENT_OCR_TIMEOUT_MS"), DEFAULT_TENCENT_TIMEOUT_MS)
        self.use_new_model = _env_flag("TENCENT_OCR_USE_NEW_MODEL", default=False)
        self.enable_image_crop = _env_flag("TENCENT_OCR_ENABLE_IMAGE_CROP", default=False)
        self.enable_only_detect_border = _env_flag("TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER", default=False)
        self.real_smoke_enabled = _env_flag("TENCENT_OCR_REAL_SMOKE", default=False)

    def is_available(self) -> tuple[bool, list[str]]:
        missing = []
        if not self.secret_id:
            missing.append("missing_tencent_secret_id")
        if not self.secret_key:
            missing.append("missing_tencent_secret_key")
        if missing:
            return False, missing
        if not self.real_smoke_enabled:
            return False, ["tencent_real_smoke_disabled"]
        return True, []

    def analyze_document(self, request: ProviderOCRRequest) -> ProviderOCRResult:
        if len(request.page_numbers) != 1:
            return ProviderOCRResult(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                source_document_id=request.source_document_id,
                task_id=request.task_id,
                provider_status="error",
                provider_error={
                    "code": "single_page_smoke_only",
                    "message": "Tencent commercial OCR adapter is gated to single-page smoke in M8-pre.",
                },
                warnings=["single_page_smoke_only"],
            )

        started = time.perf_counter()
        page_no = request.page_numbers[0]
        trace_payload: dict[str, Any] = {
            "provider": self.provider_name,
            "provider_version": self.provider_version,
            "endpoint": self.endpoint,
            "action": self.action_name,
            "version": self.version,
            "pages": [],
        }
        try:
            response_json = self._invoke_sdk(request=request, page_no=page_no)
        except TencentCloudSDKException as exc:
            error_code = str(getattr(exc, "code", "") or exc.__class__.__name__)
            error_message = str(getattr(exc, "message", "") or str(exc))
            warning = _warning_for_tencent_error(error_code)
            trace_payload["pages"].append({"page_no": page_no, "status": "error", "error_code": error_code, "error_message": error_message})
            return ProviderOCRResult(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                source_document_id=request.source_document_id,
                task_id=request.task_id,
                raw_response_ref=_write_trace_payload(request, trace_payload, suffix="failure"),
                provider_latency_ms=int((time.perf_counter() - started) * 1000),
                provider_status="error",
                provider_error={"code": error_code, "message": error_message, "page_no": page_no},
                warnings=[warning],
            )
        except Exception as exc:  # pragma: no cover - defensive
            trace_payload["pages"].append({"page_no": page_no, "status": "error", "error_message": str(exc)})
            return ProviderOCRResult(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                source_document_id=request.source_document_id,
                task_id=request.task_id,
                raw_response_ref=_write_trace_payload(request, trace_payload, suffix="failure"),
                provider_latency_ms=int((time.perf_counter() - started) * 1000),
                provider_status="error",
                provider_error={"code": "tencent_sdk_error", "message": str(exc), "page_no": page_no},
                warnings=["tencent_sdk_error"],
            )

        page_result = normalize_tencent_question_split_response(
            page_no=page_no,
            response_json=response_json,
            provider_name=self.provider_name,
            layout_only=self.layout_only,
        )
        trace_payload["pages"].append(
            {
                "page_no": page_no,
                "status": "ok",
                "response": response_json,
                "question_info_count": len((response_json.get("Response") or response_json).get("QuestionInfo") or []),
            }
        )
        return ProviderOCRResult(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            source_document_id=request.source_document_id,
            task_id=request.task_id,
            page_results=[page_result],
            raw_response_ref=_write_trace_payload(request, trace_payload, suffix="success"),
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
            provider_status="ok",
            warnings=list(page_result.warnings),
        )

    def _invoke_sdk(self, *, request: ProviderOCRRequest, page_no: int) -> dict[str, Any]:
        creds = credential.Credential(self.secret_id, self.secret_key)
        http_profile = HttpProfile(endpoint=_endpoint_host(self.endpoint), reqTimeout=max(1, int(self.timeout_ms / 1000)))
        client_profile = ClientProfile(httpProfile=http_profile, signMethod="TC3-HMAC-SHA256")
        client = ocr_client.OcrClient(creds, self.region, client_profile)
        request_model = self._build_request_model(request=request, page_no=page_no)
        response = getattr(client, self.action_name)(request_model)
        return json.loads(response.to_json_string())

    def _build_request_model(self, *, request: ProviderOCRRequest, page_no: int):
        screenshot = request.extractor.get_page_screenshot(page_no - 1, dpi=160, max_side=2200)
        if self.layout_only:
            model = models.QuestionSplitLayoutOCRRequest()
            model.EnableImageCrop = self.enable_image_crop
            model.UseNewModel = self.use_new_model
        else:
            model = models.QuestionSplitOCRRequest()
            model.EnableImageCrop = self.enable_image_crop
            model.EnableOnlyDetectBorder = self.enable_only_detect_border
            model.UseNewModel = self.use_new_model
        model.ImageBase64 = screenshot
        model.IsPdf = False
        model.PdfPageNumber = 1
        return model


class TencentQuestionSplitLayoutProvider(TencentQuestionSplitProvider):
    provider_name = "tencent_question_split_layout"
    provider_version = f"{DEFAULT_TENCENT_VERSION}:QuestionSplitLayoutOCR"
    action_name = "QuestionSplitLayoutOCR"
    layout_only = True


def _warning_for_tencent_error(error_code: str) -> str:
    lowered = error_code.lower()
    if "auth" in lowered or "secret" in lowered or "signature" in lowered:
        return "tencent_auth_error"
    if "limit" in lowered or "thrott" in lowered or "requestlimit" in lowered:
        return "tencent_rate_limited"
    return "tencent_provider_error"


def _endpoint_host(endpoint: str) -> str:
    return endpoint.replace("https://", "").replace("http://", "").strip("/") or "ocr.tencentcloudapi.com"


def _env_flag(name: str, *, default: bool) -> bool:
    value = str(os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _write_trace_payload(request: ProviderOCRRequest, payload: dict[str, Any], *, suffix: str) -> str | None:
    trace_root = _trace_root(request)
    trace_root.mkdir(parents=True, exist_ok=True)
    target = trace_root / f"{request.task_id}-{suffix}.json"
    if not request.trace_enabled:
        payload = {
            "provider": payload.get("provider"),
            "provider_version": payload.get("provider_version"),
            "endpoint": payload.get("endpoint"),
            "action": payload.get("action"),
            "version": payload.get("version"),
            "pages": [
                {
                    "page_no": page.get("page_no"),
                    "status": page.get("status"),
                    "question_info_count": page.get("question_info_count"),
                    "error_code": page.get("error_code"),
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
