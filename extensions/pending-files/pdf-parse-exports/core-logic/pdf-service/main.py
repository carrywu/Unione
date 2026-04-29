from __future__ import annotations

import os
import tempfile
import logging
import time
import asyncio

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from models import ParseByUrlRequest
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


load_dotenv()

app = FastAPI(title="Quiz PDF Service")
logger = logging.getLogger(__name__)


class TestParseRequest(BaseModel):
    url: str | None = None
    file_url: str | None = None
    pages: list[int] | None = None
    ai_config: dict[str, str] | None = None
    preview_limit: int | None = 20



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
        mark_parse_finish(True, len(result.questions), time.perf_counter() - started)
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
        mark_parse_finish(True, len(result.questions), time.perf_counter() - started)
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
    return {
        "status": "success",
        "questions_count": len(result.questions),
        "materials_count": len(result.materials),
        "stats": result.stats.model_dump(),
        "detection": result.stats.detection,
        "callback_delivered": True,
    }


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
                "stats": result.stats.model_dump(),
                "detection": result.stats.detection,
                "total_count": total,
            },
        )


def _result_payload(result, preview_limit: int | None = None, strip_images_after: int | None = None):
    payload = result.model_dump()
    payload["status"] = "success"
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
