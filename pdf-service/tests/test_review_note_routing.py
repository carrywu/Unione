import unittest

from parser_kernel.routing import should_use_question_book_kernel


class ReviewNoteRoutingTest(unittest.TestCase):
    def test_review_note_fixture_is_not_treated_as_question_book(self):
        file_name = "test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册）.pdf"
        self.assertFalse(should_use_question_book_kernel(file_name))


if __name__ == "__main__":
    unittest.main()
