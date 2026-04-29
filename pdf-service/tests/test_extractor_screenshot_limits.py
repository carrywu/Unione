import base64
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from extractor import PDFExtractor


class ExtractorScreenshotLimitsTest(unittest.TestCase):
    def test_page_screenshot_respects_max_side(self):
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "sample.pdf"
            doc = fitz.open()
            doc.new_page(width=1000, height=2000)
            doc.save(pdf_path)
            doc.close()

            extractor = PDFExtractor(str(pdf_path))
            try:
                image_b64 = extractor.get_page_screenshot(0, dpi=144, max_side=800)
                image_size = extractor.get_page_screenshot_size(0, dpi=144, max_side=800)
            finally:
                extractor.close()

            self.assertLessEqual(max(image_size["width"], image_size["height"]), 800)
            self.assertTrue(base64.b64decode(image_b64))


if __name__ == "__main__":
    unittest.main()
