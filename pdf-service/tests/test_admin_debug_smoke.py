import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class AdminDebugSmokeEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.previous_token = os.environ.get("PDF_SERVICE_INTERNAL_TOKEN")
        self.previous_internal_token = os.environ.get("INTERNAL_TOKEN")
        os.environ.pop("INTERNAL_TOKEN", None)
        os.environ["PDF_SERVICE_INTERNAL_TOKEN"] = "test-token"

    def tearDown(self):
        if self.previous_token is None:
            os.environ.pop("PDF_SERVICE_INTERNAL_TOKEN", None)
        else:
            os.environ["PDF_SERVICE_INTERNAL_TOKEN"] = self.previous_token
        if self.previous_internal_token is None:
            os.environ.pop("INTERNAL_TOKEN", None)
        else:
            os.environ["INTERNAL_TOKEN"] = self.previous_internal_token

    def test_debug_smoke_endpoint_generates_metadata(self):
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "source.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            smoke_root = Path(tmpdir) / "runs"

            def fake_smoke(pdf_path_arg: str, **kwargs):
                output = Path(kwargs["output_dir"])
                (output / "debug" / "overlays").mkdir(parents=True)
                (output / "debug" / "crops").mkdir(parents=True)
                (output / "page_screenshots").mkdir(parents=True)
                (output / "summary.json").write_text(json.dumps({"total_questions": 2}), encoding="utf-8")
                (output / "review_manifest.json").write_text("[]", encoding="utf-8")
                (output / "review_manifest.csv").write_text("question_id\n", encoding="utf-8")
                (output / "debug" / "bbox_lineage.json").write_text("[]", encoding="utf-8")
                self.assertEqual(pdf_path_arg, str(pdf_path))
                return {"page_limit": 5, "candidate_counts": {"accepted_questions": 2}}

            with patch("main._download_pdf", return_value=str(pdf_path)), patch(
                "main.DEBUG_SMOKE_ROOT",
                smoke_root,
            ), patch("main.run_visual_api_smoke", side_effect=fake_smoke):
                response = self.client.post(
                    "/admin/debug-smoke-by-url",
                    headers={"Authorization": "Bearer test-token"},
                    json={"url": "https://example.test/source.pdf", "task_id": "abc", "pages": "9-14"},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["run_id"], "task_abc_pages_9_14")
            self.assertEqual(payload["pages"], "9-14")
            self.assertEqual(payload["summary_preview"]["page_limit"], 5)
            self.assertIn("summary", payload["files"])
            self.assertIn("overlays", payload["dirs"])

    def test_debug_artifact_endpoint_reads_summary_json(self):
        with TemporaryDirectory() as tmpdir:
            smoke_root = Path(tmpdir) / "runs"
            run_dir = smoke_root / "task_abc_pages_9_14"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

            with patch("main.DEBUG_SMOKE_ROOT", smoke_root):
                response = self.client.get(
                    "/admin/debug-artifacts/task_abc_pages_9_14",
                    headers={"Authorization": "Bearer test-token"},
                    params={"path": "summary.json"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"ok": True})

    def test_debug_artifact_endpoint_rejects_path_traversal(self):
        with TemporaryDirectory() as tmpdir:
            smoke_root = Path(tmpdir) / "runs"
            (smoke_root / "task_abc_pages_9_14").mkdir(parents=True)

            with patch("main.DEBUG_SMOKE_ROOT", smoke_root):
                response = self.client.get(
                    "/admin/debug-artifacts/task_abc_pages_9_14",
                    headers={"Authorization": "Bearer test-token"},
                    params={"path": "../../etc/passwd"},
                )

            self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
