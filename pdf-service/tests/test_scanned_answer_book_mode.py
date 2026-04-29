import unittest

from answer_book_parser import detect_answer_book_mode


class FakeScannedAnswerExtractor:
    total_pages = 2
    pdf_path = "/tmp/解析篇.pdf"

    def get_page_text(self, page_num: int) -> str:
        return ""

    def get_page_images(self, page_num: int):
        return [{"bbox": [0, 0, 10, 10], "base64": "x"}]


class ScannedAnswerBookModeTest(unittest.TestCase):
    def test_scanned_answer_book_auto_mode_prefers_image(self):
        mode = detect_answer_book_mode(FakeScannedAnswerExtractor())
        self.assertEqual(mode, "image")


if __name__ == "__main__":
    unittest.main()
