"""Tests for MiMo reviewer (visual + text)."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest


class TestMimoReviewerStatus:
    def test_default_status_shows_disabled(self):
        from commercial_ocr.mimo_reviewer import mimo_review_status

        with patch.dict(os.environ, {}, clear=False):
            for k in ("MIMO_ENABLED", "MIMO_API_KEY", "MIMO_BASE_URL",
                       "MIMO_TEXT_MODEL", "MIMO_VISION_MODEL", "MIMO_TIMEOUT_MS"):
                os.environ.pop(k, None)
            status = mimo_review_status()
        assert status["enabled"] is False
        assert status["api_key_set"] is False
        assert status["real_smoke_allowed"] is False
        assert status["text_model"] == "mimo-v2.5-pro"
        assert status["vision_model"] == "mimo-v2.5"

    def test_enabled_status_shows_configured(self):
        from commercial_ocr.mimo_reviewer import mimo_review_status

        env = {
            "MIMO_ENABLED": "true",
            "MIMO_API_KEY": "test-key",
            "MIMO_BASE_URL": "https://example.com/v1",
            "MIMO_TEXT_MODEL": "mimo-v2.5-pro",
            "MIMO_VISION_MODEL": "mimo-v2.5",
            "MIMO_TIMEOUT_MS": "60000",
        }
        with patch.dict(os.environ, env, clear=False):
            status = mimo_review_status()
        assert status["enabled"] is True
        assert status["api_key_set"] is True
        assert status["real_smoke_allowed"] is True
        assert status["timeout_ms"] == 60000


class TestMimoVisualReviewMock:
    def test_visual_review_returns_skipped_when_not_configured(self):
        from commercial_ocr.mimo_reviewer import review_visual_screenshot

        with patch.dict(os.environ, {"MIMO_ENABLED": "false"}, clear=False):
            result = review_visual_screenshot(
                image_base64="fake-base64",
                context="test",
                ocr_summary="test ocr",
            )
        assert result["overall_verdict"] == "skipped"
        assert result["model"] == "mimo-v2.5"
        assert result["skipped_reason"] == "real_mimo_not_configured"
        assert "human_readable" in result
        assert "blocking_issues" in result

    def test_visual_review_returns_skipped_when_no_api_key(self):
        from commercial_ocr.mimo_reviewer import review_visual_screenshot

        env = {"MIMO_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("MIMO_API_KEY", None)
            result = review_visual_screenshot(image_base64="fake")
        assert result["overall_verdict"] == "skipped"
        assert result["skipped_reason"] == "real_mimo_not_configured"


class TestMimoTextReviewMock:
    def test_text_review_returns_skipped_when_not_configured(self):
        from commercial_ocr.mimo_reviewer import review_text_payload

        with patch.dict(os.environ, {"MIMO_ENABLED": "false"}, clear=False):
            result = review_text_payload(
                payload={"test": True},
                context="test",
            )
        assert result["overall_verdict"] == "skipped"
        assert result["model"] == "mimo-v2.5-pro"
        assert result["skipped_reason"] == "real_mimo_not_configured"
        assert result["same_material_id_for_17_20"] is True
        assert result["quality_gate_reasonable"] is True

    def test_text_review_returns_skipped_when_no_api_key(self):
        from commercial_ocr.mimo_reviewer import review_text_payload

        env = {"MIMO_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("MIMO_API_KEY", None)
            result = review_text_payload(payload={"test": True})
        assert result["overall_verdict"] == "skipped"


class TestMimoVisualReviewRealFallback:
    def test_visual_review_degrades_on_api_error(self):
        from commercial_ocr.mimo_reviewer import review_visual_screenshot

        env = {
            "MIMO_ENABLED": "true",
            "MIMO_API_KEY": "invalid-key",
            "MIMO_TIMEOUT_MS": "5000",
        }
        with patch.dict(os.environ, env, clear=False):
            result = review_visual_screenshot(image_base64="fake-base64")
        # Should degrade to skipped, not raise
        assert result["overall_verdict"] == "skipped"
        assert result["skipped_reason"] is not None
        assert "real_call_failed" in result["skipped_reason"]


class TestMimoTextReviewRealFallback:
    def test_text_review_degrades_on_api_error(self):
        from commercial_ocr.mimo_reviewer import review_text_payload

        env = {
            "MIMO_ENABLED": "true",
            "MIMO_API_KEY": "invalid-key",
            "MIMO_TIMEOUT_MS": "5000",
        }
        with patch.dict(os.environ, env, clear=False):
            result = review_text_payload(payload={"test": True})
        # Should degrade to skipped, not raise
        assert result["overall_verdict"] == "skipped"
        assert result["skipped_reason"] is not None
        assert "real_call_failed" in result["skipped_reason"]
