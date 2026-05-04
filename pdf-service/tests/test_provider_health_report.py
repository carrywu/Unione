import json
import os
import unittest
from unittest.mock import patch

import ai_client
from tools.provider_health_report import run_provider_health_checks


class ProviderHealthReportTest(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_ark_provider_config_missing_key_is_not_configured(self):
        config = ai_client.resolve_vision_provider_config("volcengine_ark_vl")

        self.assertFalse(config["configured"])
        self.assertIn("missing_api_key", config["missing"])
        self.assertEqual(config["api_mode"], "responses")
        self.assertEqual(config["endpoint"], "/responses")

    @patch("tools.provider_health_report.load_project_env")
    @patch("tools.provider_health_report.ai_client._ark_responses_json")
    @patch.dict(
        os.environ,
        {
            "ARK_API_KEY": "ark-abcdefghijklmnopqrstuvwxyz1234",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "ARK_ENDPOINT_ID": "ep-20260504082005-gvl4b",
        },
        clear=True,
    )
    def test_ark_provider_smoke_falls_back_from_endpoint_id_to_default_model(
        self,
        mock_ark_json,
        _mock_load_env,
    ):
        mock_ark_json.side_effect = [
            RuntimeError("model service not open"),
            ({"ok": True, "summary": "remote"}, {"output_text_preview": '{"ok":true}'}),
            ({"ok": True, "summary": "local"}, {"output_text_preview": '{"ok":true}'}),
        ]

        report = run_provider_health_checks(
            provider_order=["volcengine_ark_vl"],
            timeout_seconds=1.0,
        )
        ark = report["providers"]["volcengine_ark_vl"]

        self.assertEqual(ark["health"], "pass")
        self.assertEqual(ark["api_mode"], "responses")
        self.assertEqual(ark["endpoint"], "/responses")
        self.assertEqual(ark["successful_model"], "doubao-seed-1-6-vision-250815")
        self.assertEqual(ark["successful_model_type"], "model_name")
        self.assertEqual(ark["candidate_models_tested"][0]["health"], "fail")
        self.assertEqual(ark["candidate_models_tested"][0]["error_type"], "model_not_open")
        self.assertEqual(ark["candidate_models_tested"][1]["health"], "pass")
        self.assertEqual(ark["remote_smoke"]["health"], "pass")
        self.assertEqual(ark["local_smoke"]["health"], "pass")
        self.assertTrue(ark["key_present"])
        self.assertIn("***", ark["key_masked"])
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz1234", json.dumps(ark, ensure_ascii=False))

    @patch("tools.provider_health_report.load_project_env")
    @patch("tools.provider_health_report.ai_client._ark_responses_json")
    @patch.dict(
        os.environ,
        {
            "ARK_API_KEY": "ark-abcdefghijklmnopqrstuvwxyz1234",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "ARK_ENDPOINT_ID": "ep-20260504082005-gvl4b",
        },
        clear=True,
    )
    def test_ark_provider_smoke_classifies_auth_error(
        self,
        mock_ark_json,
        _mock_load_env,
    ):
        mock_ark_json.side_effect = RuntimeError("401 unauthorized")

        report = run_provider_health_checks(
            provider_order=["volcengine_ark_vl"],
            timeout_seconds=1.0,
        )
        ark = report["providers"]["volcengine_ark_vl"]

        self.assertEqual(ark["health"], "fail")
        self.assertEqual(ark["error_type"], "auth_error")
        self.assertEqual(len(ark["candidate_models_tested"]), 2)


if __name__ == "__main__":
    unittest.main()
