import os
import time
import unittest
from unittest.mock import patch

import ai_client
from parser_kernel.adapter import _classify_vision_failure, _visual_chain_timeout_seconds


def failed_result(error: str) -> dict:
    return {
        "page_type": "unknown",
        "materials": [],
        "questions": [],
        "visuals": [],
        "warnings": ["visual_model_failed"],
        "error": error,
        "schema_validation": {"exception": error},
        "raw_model_result": {"error": error},
    }


def failed_attempt(provider: str, error: str) -> dict:
    return {
        "provider": provider,
        "model": "model",
        "timeout_seconds": 120.0,
        "elapsed_ms": 120000 if provider == "qwen_vl" else 10,
        "status": "failed",
        "error_type": "timeout" if provider == "qwen_vl" else "quota_exhausted",
        "error_message": error,
        "fallback_from": "qwen_vl" if provider == "mimo_vl" else None,
    }


class _FakeHttpResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"output_text": '{"ok": true}'}


class _FakeHttpClient:
    def __init__(self, captured):
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.captured["url"] = url
        self.captured["headers"] = headers
        self.captured["json"] = json
        return _FakeHttpResponse()


class AiClientPageVisualFallbacksTest(unittest.TestCase):
    def setUp(self):
        ai_client.reset_vision_runtime_state()

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "MIMO_API_KEY": "test-mimo",
            "MIMO_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
            "ARK_API_KEY": "",
            "ARK_VISION_MODEL": "",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl,mimo_vl",
            "AI_VISUAL_MODEL": "qwen3-vl-plus",
        },
        clear=False,
    )
    @patch("ai_client.dashscope.MultiModalConversation.call")
    @patch("ai_client._call_openai_vision_provider")
    def test_parse_page_visual_skips_redundant_dashscope_sdk_fallback(
        self,
        mock_openai_provider,
        mock_dashscope_sdk,
    ):
        mock_openai_provider.side_effect = [
            (
                failed_result("provider_call_timeout_after_120.0s"),
                failed_attempt("qwen_vl", "provider_call_timeout_after_120.0s"),
            ),
            (
                failed_result("quota exhausted"),
                failed_attempt("mimo_vl", "quota exhausted"),
            ),
        ]

        result = ai_client.parse_page_visual("cXdlbi1mYXN0LXN1Y2Nlc3M=")

        self.assertEqual(mock_openai_provider.call_count, 2)
        mock_dashscope_sdk.assert_not_called()
        self.assertEqual(
            [attempt["provider"] for attempt in result["_vision_provider_attempts"]],
            ["qwen_vl", "mimo_vl"],
        )

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "MIMO_API_KEY": "test-mimo",
            "ARK_API_KEY": "",
            "ARK_VISION_MODEL": "",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl,mimo_vl",
        },
        clear=False,
    )
    def test_visual_chain_timeout_does_not_count_redundant_dashscope_sdk_slot(self):
        self.assertEqual(_visual_chain_timeout_seconds(120.0), 120.0)

    def test_runtime_config_enables_mimo_fallback_timeout_slot(self):
        with ai_client.use_config(
            {
                "dashscope_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "mimo_api_key": "test-mimo",
                "ark_api_key": "",
                "ark_vision_model": "",
                "vision_ai_provider_order": "qwen_vl,mimo_vl",
            }
        ):
            self.assertEqual(_visual_chain_timeout_seconds(120.0), 120.0)

    def test_runtime_config_overrides_provider_timeout(self):
        with ai_client.use_config(
            {
                "vision_ai_provider_timeout_seconds": "20",
            }
        ):
            self.assertEqual(ai_client._vision_provider_timeout_seconds(), 20.0)

    def test_ranked_provider_order_preserves_requested_order(self):
        with ai_client.use_config(
            {
                "ark_api_key": "ark-test",
                "ark_vision_model": "ep-ark",
                "dashscope_api_key": "qwen-test",
                "visual_model": "qwen3-vl-plus",
                "vision_ai_provider_order": "volcengine_ark_vl,qwen_vl",
            }
        ):
            self.assertEqual(
                ai_client.ranked_vision_provider_order(),
                ["volcengine_ark_vl", "qwen_vl"],
            )
            self.assertEqual(
                ai_client.configured_vision_provider_order(),
                ["volcengine_ark_vl", "qwen_vl"],
            )

    def test_page_timeout_budget_prevents_late_qwen_fallback(self):
        with ai_client.use_config(
            {
                "ark_api_key": "ark-test",
                "ark_base_url": "https://ark.example.com/v3",
                "ark_endpoint_id": "ep-test",
                "dashscope_api_key": "qwen-test",
                "dashscope_base_url": "https://dashscope.example.com/compatible-mode/v1",
                "visual_model": "qwen3-vl-plus",
                "vision_ai_provider_order": "volcengine_ark_vl,qwen_vl",
                "vision_ai_timeout_seconds": "0.1",
                "vision_ai_provider_timeout_seconds": "0.1",
            }
        ):
            with patch("ai_client._call_openai_vision_provider") as mock_qwen:

                def slow_ark(**kwargs):
                    time.sleep(0.15)
                    return (
                        failed_result("provider_call_timeout_after_0.1s"),
                        {
                            "provider": "volcengine_ark_vl",
                            "model": "ep-test",
                            "timeout_seconds": kwargs["timeout_seconds"],
                            "elapsed_ms": 150,
                            "status": "failed",
                            "error_type": "timeout",
                            "error_message": "provider_call_timeout_after_0.1s",
                            "fallback_from": None,
                        },
                    )

                with patch("ai_client._call_ark_vision_provider", side_effect=slow_ark):
                    result = ai_client.parse_page_visual("ZmFrZS1wYWdl")

        mock_qwen.assert_not_called()
        self.assertEqual(
            [attempt["provider"] for attempt in result["_vision_provider_attempts"]],
            ["volcengine_ark_vl"],
        )
        self.assertIn("vision_page_timeout", result["warnings"])

    def test_classify_vision_failure_allows_successful_provider_fallback(self):
        result = {
            "page_type": "question",
            "materials": [{"temp_id": "m1", "content": "材料"}],
            "questions": [{"index": 11, "content": "题干"}],
            "visuals": [],
            "warnings": ["semantic_questions_missing_use_questions_fallback"],
            "error": None,
            "schema_validation": {"normalized_question_count": 1},
            "_vision_provider_attempts": [
                failed_attempt("qwen_vl", "provider_call_timeout_after_120.0s"),
                {
                    "provider": "mimo_vl",
                    "model": "mimo-v2.5",
                    "timeout_seconds": 120.0,
                    "elapsed_ms": 75652,
                    "status": "ok",
                    "error_type": None,
                    "error_message": None,
                    "fallback_from": "qwen_vl",
                },
            ],
        }

        self.assertIsNone(_classify_vision_failure(result))

    @patch.dict(
        os.environ,
        {
            "ARK_API_KEY": "ark-test",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "ARK_ENDPOINT_ID": "ep-20260504082005-gvl4b",
            "ARK_VISION_MODEL": "doubao-seed-1-6-vision-250815",
        },
        clear=True,
    )
    def test_ark_candidate_priority_prefers_endpoint_id_before_model_name(self):
        config = ai_client.resolve_vision_provider_config("volcengine_ark_vl")

        self.assertEqual(config["api_mode"], "responses")
        self.assertEqual(config["endpoint"], "/responses")
        self.assertFalse(config["supports_chat_completions"])
        self.assertTrue(config["supports_responses"])
        self.assertEqual(
            [candidate["model"] for candidate in config["model_candidates"][:2]],
            ["ep-20260504082005-gvl4b", "doubao-seed-1-6-vision-250815"],
        )
        self.assertEqual(config["model_candidates"][0]["type"], "endpoint_id")
        self.assertEqual(len(config["model_candidates"]), 2)

    def test_ark_responses_payload_uses_responses_api_schema(self):
        captured = {}
        with patch("ai_client.httpx.Client", return_value=_FakeHttpClient(captured)):
            response = ai_client._ark_responses_request(
                api_key="ark-test",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                model="ep-20260504082005-gvl4b",
                input_payload=ai_client._ark_responses_input(
                    "你看见了什么？",
                    "https://example.com/demo.png",
                ),
                responses_path="/responses",
                timeout=1.0,
            )

        self.assertEqual(response["output_text"], '{"ok": true}')
        self.assertEqual(captured["url"], "https://ark.cn-beijing.volces.com/api/v3/responses")
        self.assertEqual(captured["json"]["model"], "ep-20260504082005-gvl4b")
        self.assertIn("input", captured["json"])
        self.assertEqual(captured["json"]["input"][0]["content"][0]["type"], "input_image")
        self.assertEqual(captured["json"]["input"][0]["content"][1]["type"], "input_text")
        self.assertNotIn("messages", captured["json"])

    def test_responses_output_text_supports_output_text_and_nested_output(self):
        self.assertEqual(
            ai_client._responses_output_text({"output_text": '{"ok": true}'}),
            '{"ok": true}',
        )
        self.assertEqual(
            ai_client._responses_output_text(
                {
                    "output": [
                        {
                            "content": [
                                {
                                    "text": "nested text",
                                }
                            ]
                        }
                    ]
                }
            ),
            "nested text",
        )

    @patch("ai_client._ark_responses_json")
    def test_ark_candidate_fallback_uses_second_model_when_endpoint_fails(self, mock_ark_json):
        mock_ark_json.side_effect = [
            RuntimeError("model service not open"),
            (
                {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [{"index": 17, "content": "第17题"}],
                    "visuals": [],
                },
                {"output_text_preview": '{"ok":true}'},
            ),
        ]

        result, attempt = ai_client._call_ark_vision_provider(
            provider="volcengine_ark_vl",
            api_key="ark-test",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model_candidates=[
                {"model": "ep-20260504082005-gvl4b", "type": "endpoint_id"},
                {"model": "doubao-seed-1-6-vision-250815", "type": "model_name"},
            ],
            page_b64="ZmFrZS1wYWdl",
            timeout_seconds=1.0,
            responses_path="/responses",
        )

        self.assertEqual(attempt["status"], "ok")
        self.assertEqual(attempt["model"], "doubao-seed-1-6-vision-250815")
        self.assertEqual(result["questions"][0]["index"], 17)
        self.assertEqual(len(attempt["candidate_attempts"]), 2)
        self.assertEqual(attempt["candidate_attempts"][0]["error_type"], "model_not_open")

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "ARK_API_KEY": "ark-test",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "ARK_ENDPOINT_ID": "ep-20260504082005-gvl4b",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl,volcengine_ark_vl,mimo_vl",
            "AI_VISUAL_MODEL": "qwen3-vl-plus",
            "VISION_AI_SOFT_TIMEOUT_SECONDS": "0.01",
            "VISION_AI_PROVIDER_TIMEOUT_SECONDS": "0.2",
        },
        clear=False,
    )
    @patch("ai_client.dashscope.MultiModalConversation.call")
    @patch("ai_client._call_ark_vision_provider")
    @patch("ai_client._call_openai_vision_provider")
    def test_parse_page_visual_hedges_to_ark_after_qwen_soft_timeout(
        self,
        mock_openai_provider,
        mock_ark_provider,
        mock_dashscope_sdk,
    ):
        def delayed_qwen(*args, **kwargs):
            self.assertEqual(kwargs["provider"], "qwen_vl")
            time.sleep(0.05)
            return (
                {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [{"index": 1, "content": "Qwen 慢返回"}],
                    "visuals": [],
                },
                {
                    "provider": "qwen_vl",
                    "model": "qwen3-vl-plus",
                    "timeout_seconds": 0.2,
                    "elapsed_ms": 50,
                    "status": "ok",
                    "error_type": None,
                    "error_message": None,
                    "fallback_from": None,
                },
            )

        mock_openai_provider.side_effect = delayed_qwen
        mock_ark_provider.return_value = (
            {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [{"index": 17, "content": "第17题"}],
                "visuals": [],
            },
            {
                "provider": "volcengine_ark_vl",
                "model": "ep-20260504082005-gvl4b",
                "timeout_seconds": 0.2,
                "elapsed_ms": 5,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "fallback_from": "qwen_vl",
                "api_mode": "responses",
                "endpoint": "/responses",
            },
        )

        result = ai_client.parse_page_visual("ZmFrZS1wYWdl")

        self.assertEqual(mock_openai_provider.call_count, 1)
        self.assertEqual(mock_ark_provider.call_count, 1)
        mock_dashscope_sdk.assert_not_called()
        self.assertEqual(result["_vision_provider"], "volcengine_ark_vl")
        self.assertEqual(result["questions"][0]["index"], 17)
        self.assertIsNone(_classify_vision_failure(result))

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "ARK_API_KEY": "ark-test",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "ARK_ENDPOINT_ID": "ep-20260504082005-gvl4b",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl,volcengine_ark_vl",
            "AI_VISUAL_MODEL": "qwen3-vl-plus",
            "VISION_AI_SOFT_TIMEOUT_SECONDS": "0.05",
            "VISION_AI_PROVIDER_TIMEOUT_SECONDS": "0.2",
        },
        clear=False,
    )
    @patch("ai_client._call_ark_vision_provider")
    @patch("ai_client._call_openai_vision_provider")
    def test_qwen_fast_success_does_not_call_backup(self, mock_openai_provider, mock_ark_provider):
        mock_openai_provider.return_value = (
            {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [{"index": 3, "content": "Qwen 快速成功"}],
                "visuals": [],
            },
            {
                "provider": "qwen_vl",
                "model": "qwen3-vl-plus",
                "timeout_seconds": 0.2,
                "elapsed_ms": 2,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "fallback_from": None,
            },
        )

        result = ai_client.parse_page_visual("ZmFrZS1wYWdl")

        self.assertEqual(result["_vision_provider"], "qwen_vl")
        self.assertEqual(mock_openai_provider.call_count, 1)
        mock_ark_provider.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "ARK_API_KEY": "ark-test",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "ARK_ENDPOINT_ID": "ep-20260504082005-gvl4b",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl,volcengine_ark_vl",
            "AI_VISUAL_MODEL": "qwen3-vl-plus",
            "VISION_AI_SOFT_TIMEOUT_SECONDS": "0.01",
            "VISION_AI_PROVIDER_TIMEOUT_SECONDS": "0.2",
        },
        clear=False,
    )
    @patch("ai_client._call_ark_vision_provider")
    @patch("ai_client._call_openai_vision_provider")
    def test_late_qwen_result_does_not_override_ark_winner(self, mock_openai_provider, mock_ark_provider):
        def delayed_qwen(*args, **kwargs):
            time.sleep(0.05)
            return (
                {
                    "page_type": "question",
                    "warnings": [],
                    "materials": [],
                    "questions": [{"index": 99, "content": "Qwen 晚到结果"}],
                    "visuals": [],
                },
                {
                    "provider": "qwen_vl",
                    "model": "qwen3-vl-plus",
                    "timeout_seconds": 0.2,
                    "elapsed_ms": 50,
                    "status": "ok",
                    "error_type": None,
                    "error_message": None,
                    "fallback_from": None,
                },
            )

        mock_openai_provider.side_effect = delayed_qwen
        mock_ark_provider.return_value = (
            {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [{"index": 18, "content": "Ark 先返回"}],
                "visuals": [],
            },
            {
                "provider": "volcengine_ark_vl",
                "model": "ep-20260504082005-gvl4b",
                "timeout_seconds": 0.2,
                "elapsed_ms": 3,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "fallback_from": "qwen_vl",
            },
        )

        result = ai_client.parse_page_visual("ZmFrZS1wYWdl")

        self.assertEqual(result["_vision_provider"], "volcengine_ark_vl")
        self.assertEqual(result["questions"][0]["index"], 18)

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "MIMO_API_KEY": "test-mimo",
            "MIMO_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl,mimo_vl",
            "AI_VISUAL_MODEL": "qwen3-vl-plus",
            "VISION_AI_PROVIDER_TIMEOUT_SECONDS": "0.2",
        },
        clear=False,
    )
    @patch("ai_client._call_openai_vision_provider")
    def test_mimo_quota_exhausted_enters_cooldown(self, mock_openai_provider):
        def first_round(*args, **kwargs):
            provider = kwargs["provider"]
            if provider == "qwen_vl":
                return failed_result("provider_call_timeout_after_0.2s"), {
                    "provider": "qwen_vl",
                    "model": "qwen3-vl-plus",
                    "timeout_seconds": 0.2,
                    "elapsed_ms": 200,
                    "status": "failed",
                    "error_type": "timeout",
                    "error_message": "provider_call_timeout_after_0.2s",
                    "fallback_from": None,
                }
            return failed_result("429 quota exhausted"), {
                "provider": "mimo_vl",
                "model": "mimo-v2.5",
                "timeout_seconds": 0.2,
                "elapsed_ms": 1,
                "status": "failed",
                "error_type": "quota_exhausted",
                "error_message": "429 quota exhausted",
                "fallback_from": "qwen_vl",
            }

        mock_openai_provider.side_effect = first_round
        ai_client.parse_page_visual("ZmFrZS1wYWdl")
        first_call_count = mock_openai_provider.call_count

        mock_openai_provider.reset_mock()
        mock_openai_provider.side_effect = first_round
        ai_client.parse_page_visual("Wm1GclpTMXdZV2Rs")

        self.assertEqual(first_call_count, 2)
        self.assertEqual(mock_openai_provider.call_count, 1)

    @patch.dict(
        os.environ,
        {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "VISION_AI_PROVIDER_ORDER": "qwen_vl",
            "AI_VISUAL_MODEL": "qwen3-vl-plus",
        },
        clear=False,
    )
    @patch("ai_client._call_openai_vision_provider")
    def test_provider_cache_hit_skips_duplicate_billable_call(self, mock_openai_provider):
        mock_openai_provider.return_value = (
            {
                "page_type": "question",
                "warnings": [],
                "materials": [],
                "questions": [{"index": 6, "content": "缓存命中题干"}],
                "visuals": [],
            },
            {
                "provider": "qwen_vl",
                "model": "qwen3-vl-plus",
                "timeout_seconds": 120.0,
                "elapsed_ms": 2,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "fallback_from": None,
            },
        )

        first = ai_client.parse_page_visual("ZmFrZS1wYWdl")
        second = ai_client.parse_page_visual("ZmFrZS1wYWdl")

        self.assertEqual(mock_openai_provider.call_count, 1)
        self.assertEqual(first["questions"][0]["index"], 6)
        self.assertEqual(second["questions"][0]["index"], 6)


if __name__ == "__main__":
    unittest.main()
