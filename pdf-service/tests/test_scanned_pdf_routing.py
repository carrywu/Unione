import unittest

from parser_kernel.routing import classify_pdf_kind, filename_hint, routing_decision


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

    def test_question_book_filename_is_hint_not_final_kind(self):
        kind = classify_pdf_kind(
            file_name="题本篇.pdf",
            total_pages=4,
            text_lengths=[900, 850, 920, 880],
        )
        self.assertEqual(filename_hint("题本篇.pdf"), "scanned_question_book_hint")
        self.assertEqual(kind, "text_layer_book")

    def test_routing_decision_exposes_page_reality_evidence(self):
        decision = routing_decision(
            file_name="题本篇.pdf",
            total_pages=8,
            text_lengths=[0] * 8,
            page_reality={"questionLikeScore": 0.8, "blankPageScore": 0.1},
        )
        self.assertEqual(decision["filenameHint"], "scanned_question_book_hint")
        self.assertEqual(decision["actualKind"], "scanned_question_book")
        self.assertEqual(decision["recommendedStrategy"], "scanned_kernel")


if __name__ == "__main__":
    unittest.main()
