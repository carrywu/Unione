from __future__ import annotations

import os
import base64
import tempfile
import logging
import time
import asyncio
import re
import shutil
from pathlib import Path

import fitz
import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from answer_book_parser import parse_answer_book
import ai_client
from models import ParseAnswerBookByUrlRequest, ParseByUrlRequest
import prompt_loader
from monitor import (
    mark_parse_finish,
    mark_parse_start,
    masked_config_payload,
    stats_payload,
    status_payload,
    update_runtime_config,
)
from pipeline import parse_pdf
from tools.visual_api_smoke import run_visual_api_smoke


load_dotenv()

app = FastAPI(title="Quiz PDF Service")
logger = logging.getLogger(__name__)
DEBUG_SMOKE_ROOT = Path(__file__).resolve().parent / "tmp" / "visual-api-smoke" / "tasks"
_debug_smoke_lock = asyncio.Lock()


class TestParseRequest(BaseModel):
    url: str | None = None
    file_url: str | None = None
    pages: list[int] | None = None
    ai_config: dict[str, str] | None = None
    preview_limit: int | None = 20


class OcrRegionRequest(BaseModel):
    pdf_path_or_url: str
    page_num: int
    bbox: list[float]
    mode: str
    ai_config: dict[str, str] | None = None


class ReadabilityReviewRequest(BaseModel):
    question: dict
    ai_config: dict[str, str] | None = None


class DebugSmokeByUrlRequest(BaseModel):
    url: str
    task_id: str | None = None
    pages: str = "9-14"
    clean_output: bool = False
    refresh_cache: bool = False
    retry_failed_pages_only: bool = False



class RuntimeConfigUpdate(BaseModel):
    ai_provider_vision: str | None = None
    ai_provider_text: str | None = None
    qwen_api_key: str | None = None
    deepseek_api_key: str | None = None
    cache_ttl: int | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/parse")
async def parse(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail={"error": "only pdf is supported"})

    path = await _save_temp(await file.read())
    started = time.perf_counter()
    mark_parse_start()
    try:
        result = await _run_parse(path)
        mark_parse_finish(not _is_zero_question_result(result), len(result.questions), time.perf_counter() - started)
        return _result_payload(result)
    except Exception as exc:
        mark_parse_finish(False, 0, time.perf_counter() - started)
        logger.error("解析失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
    finally:
        _remove(path)


@app.post("/parse-by-url")
async def parse_by_url(payload: ParseByUrlRequest):
    try:
        path = await _download_pdf(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"download pdf failed: {exc}"}) from exc

    started = time.perf_counter()
    mark_parse_start()
    try:
        result = await _run_parse(path, payload.url, payload.ai_config)
        mark_parse_finish(not _is_zero_question_result(result), len(result.questions), time.perf_counter() - started)
        if payload.callback_url:
            await _send_parse_callback(
                payload.callback_url,
                payload.callback_token,
                result,
                max(1, payload.callback_batch_size or 20),
            )
            return _summary_payload(result)
        return _result_payload(result)
    except Exception as exc:
        mark_parse_finish(False, 0, time.perf_counter() - started)
        logger.error("解析失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
    finally:
        _remove(path)


@app.post("/parse-answer-book-by-url")
async def parse_answer_book_by_url(payload: ParseAnswerBookByUrlRequest):
    if payload.mode not in {"text", "image", "auto"}:
        raise HTTPException(status_code=400, detail={"error": "mode must be text, image, or auto"})
    try:
        path = await _download_pdf(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"download pdf failed: {exc}"}) from exc

    try:
        result = parse_answer_book(path, payload.mode, payload.ai_config)
        return result.model_dump()
    except Exception as exc:
        logger.error("答案册解析失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
    finally:
        _remove(path)


@app.post("/ocr-region")
async def ocr_region(payload: OcrRegionRequest):
    if payload.mode not in {"stem", "options", "material", "analysis", "image"}:
        raise HTTPException(status_code=400, detail={"error": "invalid mode"})
    if len(payload.bbox) != 4:
        raise HTTPException(status_code=400, detail={"error": "bbox must contain 4 numbers"})

    path = payload.pdf_path_or_url
    should_remove = False
    if path.startswith("http://") or path.startswith("https://"):
        try:
            path = await _download_pdf(path)
            should_remove = True
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"error": f"download pdf failed: {exc}"}) from exc

    try:
        return await asyncio.to_thread(_ocr_region_sync, path, payload)
    except Exception as exc:
        logger.error("框选 OCR 失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
    finally:
        if should_remove:
            _remove(path)


@app.post("/review-question-readability")
async def review_question_readability(payload: ReadabilityReviewRequest):
    try:
        return await asyncio.to_thread(_review_question_readability_sync, payload)
    except Exception as exc:
        logger.error("题目可读性预审失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


def _review_question_readability_sync(payload: ReadabilityReviewRequest):
    with ai_client.use_config(payload.ai_config):
        return ai_client.review_question_readability(payload.question)


async def _download_pdf(url: str) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(url)
        response.raise_for_status()
    return await _save_temp(response.content)


def _require_internal_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("INTERNAL_TOKEN") or os.getenv("PDF_SERVICE_INTERNAL_TOKEN")
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})


@app.get("/status")
async def status():
    return status_payload()


@app.get("/stats")
async def stats():
    return stats_payload()


@app.post("/admin/cache/invalidate")
async def invalidate_cache(_: None = Depends(_require_internal_token)):
    prompt_loader.invalidate()
    return {"cleared": True}


@app.post("/admin/test-parse")
async def test_parse(payload: TestParseRequest, _: None = Depends(_require_internal_token)):
    url = payload.url or payload.file_url
    if not url:
        raise HTTPException(status_code=400, detail={"error": "url is required"})

    source_path = await _download_pdf(url)
    parse_path = source_path
    try:
        selected_pages = payload.pages if payload.pages else [0, 1, 2]
        parse_path = _copy_selected_pages(source_path, selected_pages)
        result = await _run_parse(parse_path, url, payload.ai_config)
        return _result_payload(result, preview_limit=payload.preview_limit or 20, strip_images_after=5)
    finally:
        _remove(source_path)
        if parse_path != source_path:
            _remove(parse_path)


@app.post("/admin/debug-smoke-by-url")
async def debug_smoke_by_url(
    payload: DebugSmokeByUrlRequest,
    _: None = Depends(_require_internal_token),
):
    source_path = await _download_pdf(payload.url)
    try:
        run_id = _debug_smoke_run_id(payload.task_id, payload.pages)
        output_dir = DEBUG_SMOKE_ROOT / run_id
        async with _debug_smoke_lock:
            if payload.clean_output and output_dir.exists() and not payload.retry_failed_pages_only:
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            summary = await asyncio.to_thread(
                run_visual_api_smoke,
                source_path,
                pages=payload.pages,
                output_dir=str(output_dir),
                retry_failed_pages_only=payload.retry_failed_pages_only,
                refresh_cache=payload.refresh_cache,
            )
        return _debug_smoke_metadata(run_id, payload.pages, output_dir, summary)
    except Exception as exc:
        logger.error("visual smoke debug failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
    finally:
        _remove(source_path)


@app.get("/admin/debug-artifacts/{run_id}")
async def debug_artifact(
    run_id: str,
    path: str = Query(...),
    _: None = Depends(_require_internal_token),
):
    run_dir = _debug_smoke_run_dir(run_id)
    artifact_path = _resolve_debug_artifact_path(run_dir, path)
    return FileResponse(str(artifact_path))


@app.get("/admin/config")
async def get_runtime_config(_: None = Depends(_require_internal_token)):
    return masked_config_payload()


@app.put("/admin/config")
async def update_runtime_config_endpoint(
    payload: RuntimeConfigUpdate,
    _: None = Depends(_require_internal_token),
):
    updated = update_runtime_config(payload.model_dump(exclude_unset=True))
    return {"updated": updated}


def _summary_payload(result):
    failed = _is_zero_question_result(result)
    return {
        "status": "failed" if failed else "success",
        "error": "未解析到题目" if failed else None,
        "questions_count": len(result.questions),
        "materials_count": len(result.materials),
        "stats": result.stats.model_dump(),
        "warnings": result.stats.warnings,
        "detection": result.stats.detection,
        "callback_delivered": True,
    }


def _debug_smoke_run_id(task_id: str | None, pages: str) -> str:
    prefix = f"task_{task_id}" if task_id else f"run_{int(time.time())}"
    return f"{_debug_slug(prefix)}_pages_{_debug_slug(pages)}"


def _debug_slug(value: object) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    slug = slug.replace("-", "_").strip("._")
    return slug[:120] or "default"


def _debug_smoke_metadata(run_id: str, pages: str, output_dir: Path, summary: dict):
    files = {
        "summary": "summary.json",
        "page_parse_summary": "page_parse_summary.json",
        "review_manifest_json": "review_manifest.json",
        "review_manifest_csv": "review_manifest.csv",
        "raw_model_response": "raw_model_response.json",
        "rejected_candidates": "rejected_candidates.json",
        "visual_pages": "debug/visual_pages.json",
        "bbox_lineage": "debug/bbox_lineage.json",
    }
    existing_files = {
        key: value
        for key, value in files.items()
        if (output_dir / value).is_file()
    }
    dirs = {
        "overlays": "debug/overlays",
        "crops": "debug/crops",
        "page_screenshots": "page_screenshots",
    }
    existing_dirs = {
        key: value
        for key, value in dirs.items()
        if (output_dir / value).is_dir()
    }
    return {
        "run_id": run_id,
        "pages": pages,
        "output_dir": str(output_dir),
        "files": existing_files,
        "dirs": existing_dirs,
        "summary_preview": {
            "page_limit": summary.get("page_limit"),
            "pages_attempted": summary.get("pages_attempted"),
            "cache_hits": summary.get("cache_hits"),
            "cache_misses": summary.get("cache_misses"),
            "failed_pages": summary.get("failed_pages") or [],
            "timeout_pages": summary.get("timeout_pages") or [],
            "candidate_counts": summary.get("candidate_counts") or {},
        },
    }


def _debug_smoke_run_dir(run_id: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or "\0" in run_id:
        raise HTTPException(status_code=400, detail={"error": "invalid run_id"})
    root = DEBUG_SMOKE_ROOT.resolve()
    run_dir = (root / run_id).resolve()
    if os.path.commonpath([str(root), str(run_dir)]) != str(root):
        raise HTTPException(status_code=400, detail={"error": "invalid run_id"})
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail={"error": "debug run not found"})
    return run_dir


def _resolve_debug_artifact_path(run_dir: Path, relative_path: str) -> Path:
    if (
        not relative_path
        or "\0" in relative_path
        or Path(relative_path).is_absolute()
        or any(part == ".." for part in Path(relative_path).parts)
    ):
        raise HTTPException(status_code=400, detail={"error": "invalid artifact path"})
    root = run_dir.resolve()
    target = (root / relative_path).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise HTTPException(status_code=400, detail={"error": "invalid artifact path"})
    if not target.is_file():
        raise HTTPException(status_code=404, detail={"error": "artifact not found"})
    return target


async def _send_parse_callback(
    callback_url: str,
    callback_token: str | None,
    result,
    batch_size: int,
) -> None:
    headers = {"X-Internal-Token": callback_token} if callback_token else None
    timeout = httpx.Timeout(120.0, connect=10.0)
    base_url = callback_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        if result.materials:
            await client.post(
                f"{base_url}/materials",
                json={"materials": [material.model_dump() for material in result.materials]},
            )
        questions = [question.model_dump() for question in result.questions]
        total = len(questions)
        for start in range(0, total, batch_size):
            batch = questions[start : start + batch_size]
            await client.post(
                f"{base_url}/questions",
                json={
                    "questions": batch,
                    "batch_start": start,
                    "batch_size": len(batch),
                    "total": total,
                },
            )
        await client.post(
            f"{base_url}/finish",
            json={
                "status": "failed" if _is_zero_question_result(result) else "success",
                "error": "未解析到题目" if _is_zero_question_result(result) else None,
                "warnings": result.stats.warnings,
                "stats": result.stats.model_dump(),
                "detection": result.stats.detection,
                "total_count": total,
                "done_count": total,
            },
        )


def _result_payload(result, preview_limit: int | None = None, strip_images_after: int | None = None):
    payload = result.model_dump()
    failed = _is_zero_question_result(result)
    payload["status"] = "failed" if failed else "success"
    if failed:
        payload["error"] = "未解析到题目"
    payload["warnings"] = payload.get("stats", {}).get("warnings") or []
    payload["detection"] = payload.get("stats", {}).get("detection")

    questions = payload.get("questions", [])
    if preview_limit is not None and preview_limit >= 0:
        payload["preview"] = {
            "limited": len(questions) > preview_limit,
            "returned_questions": min(len(questions), preview_limit),
            "total_questions": len(questions),
        }
        questions = questions[:preview_limit]
        payload["questions"] = questions

    if strip_images_after is not None:
        for index, question in enumerate(questions):
            if index >= strip_images_after:
                question["images"] = []
        # Admin test-parse only previews question cards; material images can make
        # responses very large and are unnecessary for the monitoring panel.
        for material in payload.get("materials", []):
            material["images"] = []

    return payload


def _is_zero_question_result(result) -> bool:
    return len(getattr(result, "questions", []) or []) == 0


def _ocr_region_sync(path: str, payload: OcrRegionRequest):
    doc = fitz.open(path)
    try:
        page_index = max(0, min(payload.page_num - 1, len(doc) - 1))
        page = doc[page_index]
        rect = fitz.Rect(*[float(value) for value in payload.bbox]) & page.rect
        if rect.is_empty or rect.width < 2 or rect.height < 2:
            raise ValueError("empty bbox")

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
        image_base64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
        text = ""
        options: dict[str, str] = {}
        source = "manual_crop"
        confidence = 1.0
        warnings: list[str] = []

        if payload.mode != "image":
            text = page.get_text("text", clip=rect).strip()
            text = _clean_region_text(text, payload.mode)
            options = _split_options(text) if payload.mode == "options" else {}
            if text and (payload.mode != "options" or options):
                source = "pdf_text_layer"
                confidence = 0.88
            else:
                with ai_client.use_config(payload.ai_config):
                    visual = ai_client.ocr_region_visual(image_base64, payload.mode)
                text = _clean_region_text(str(visual.get("text") or ""), payload.mode)
                options = _split_options(text) if payload.mode == "options" else {}
                if not options and isinstance(visual.get("options"), dict):
                    options = {
                        key: str(visual["options"].get(key) or "")
                        for key in ["A", "B", "C", "D"]
                        if visual["options"].get(key)
                    }
                source = "vision_model"
                confidence = float(visual.get("confidence") or 0.65)
                warnings.extend(str(item) for item in visual.get("warnings") or [])

        return {
            "text": text,
            "options": options,
            "image_base64": image_base64,
            "page_num": page_index + 1,
            "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
            "confidence": confidence,
            "source": source,
            "warnings": warnings,
            "pdf_width": page.rect.width,
            "pdf_height": page.rect.height,
        }
    finally:
        doc.close()


def _clean_region_text(text: str, mode: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "\n").splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if not line:
            continue
        if re_match_header_footer(line):
            continue
        if mode == "stem" and re_match_option(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def re_match_header_footer(line: str) -> bool:
    import re

    if re.fullmatch(r"\d{1,4}", line):
        return True
    return bool(
        re.search(
            r"(资料分析题库|夸夸刷|原创笔记|倒卖搬运|第[一二三四五六七八九十百千万\d]+[章节])",
            line,
        )
    )


def re_match_option(line: str) -> bool:
    import re

    return bool(re.match(r"^[A-D]\s*[.、．]\s*", line, re.I))


def _split_options(text: str) -> dict[str, str]:
    import re

    compact = re.sub(r"\s+", " ", text).strip()
    matches = list(re.finditer(r"([A-D])\s*[.、．]\s*", compact, re.I))
    options: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = match.group(1).upper()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(compact)
        value = compact[start:end].strip()
        if value:
            options[key] = value
    return options


def _copy_selected_pages(pdf_path: str, pages: list[int]) -> str:
    import fitz

    source = fitz.open(pdf_path)
    target = fitz.open()
    try:
        max_page = len(source) - 1
        valid_pages = [page for page in pages if 0 <= page <= max_page]
        if not valid_pages:
            valid_pages = list(range(min(3, len(source))))
        for page in valid_pages:
            target.insert_pdf(source, from_page=page, to_page=page)
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        target.save(path)
        return path
    finally:
        target.close()
        source.close()


async def _run_parse(
    pdf_path: str,
    pdf_url: str | None = None,
    ai_config: dict[str, str] | None = None,
):
    """Run parsing away from the FastAPI event loop.

    The pipeline performs CPU-heavy PyMuPDF work and blocking AI SDK calls.
    Running it in a worker thread keeps monitoring endpoints such as /status
    and /stats responsive while a large PDF is being parsed.
    """
    return await asyncio.to_thread(
        lambda: asyncio.run(parse_pdf(pdf_path, pdf_url, ai_config)),
    )


async def _save_temp(content: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as tmp:
        tmp.write(content)
    return path


def _remove(path: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
