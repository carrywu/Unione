import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from debug_writer import write_debug_bundle
from validator import validate_and_clean


class ScannedDebugArtifactsTest(unittest.TestCase):
    def test_validate_and_clean_exposes_rejected_candidates(self):
        result = validate_and_clean(
            [
                {"index": 1, "content": "目录........1"},
                {"index": 2, "content": "abc"},
                {"index": 3, "content": "这是有效题干内容", "option_a": "甲", "option_b": "乙"},
            ],
            [],
        )
        rejected = result.get("rejected_candidates") or []
        self.assertEqual(result["stats"]["total"], 1)
        self.assertEqual(len(rejected), 2)
        reasons = {item.get("reason") for item in rejected}
        self.assertIn("toc_line", reasons)
        self.assertIn("content_too_short", reasons)

    def test_debug_bundle_writes_scanned_diagnostic_artifacts(self):
        with TemporaryDirectory() as tmpdir:
            write_debug_bundle(
                tmpdir,
                raw_model_response=[{"page_num": 1, "raw_result": {"questions": []}}],
                rejected_candidates=[{"index": 1, "reason": "content_too_short"}],
                page_parse_summary={"detector": {"type": "visual_heavy"}},
            )
            debug_dir = Path(tmpdir) / "debug"
            self.assertTrue((debug_dir / "raw_model_response.json").exists())
            self.assertTrue((debug_dir / "rejected_candidates.json").exists())
            self.assertTrue((debug_dir / "page_parse_summary.json").exists())
            payload = json.loads((debug_dir / "page_parse_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["detector"]["type"], "visual_heavy")


if __name__ == "__main__":
    unittest.main()
