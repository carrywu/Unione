import unittest

from parser_kernel.routing import classify_pdf_kind


class ScannedPdfRoutingTest(unittest.TestCase):
    def test_scanned_question_book_is_not_treated_as_text_layer_book(self):
        kind = classify_pdf_kind(
            file_name="题本篇.pdf",
            total_pages=12,
            text_lengths=[0] * 12,
        )
        self.assertEqual(kind, "scanned_question_book")

    def test_scanned_answer_book_is_not_treated_as_question_book(self):
        kind = classify_pdf_kind(
            file_name="解析篇.pdf",
            total_pages=10,
            text_lengths=[0] * 10,
        )
        self.assertEqual(kind, "scanned_answer_book")


if __name__ == "__main__":
    unittest.main()
