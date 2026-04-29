import unittest

from models import PageContent, TextBlock
from question_splitter import split_questions


def make_page(page_num: int, text: str, blocks: list[tuple[list[float], str]]) -> PageContent:
    return PageContent(
        page_num=page_num,
        text=text,
        blocks=[TextBlock(bbox=bbox, text=block_text) for bbox, block_text in blocks],
        regions=[],
    )


class ParserKernelSemanticTest(unittest.TestCase):
    def test_directory_and_teaching_text_do_not_become_questions(self):
        page = make_page(
            1,
            "第一章 资料分析........12\n方法技巧\n1. 下列说法正确的是？\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n",
            [
                ([0, 0, 100, 10], "第一章 资料分析........12"),
                ([0, 20, 100, 30], "方法技巧"),
                ([0, 40, 100, 50], "1. 下列说法正确的是？"),
                ([0, 52, 100, 62], "A. 甲"),
                ([0, 64, 100, 74], "B. 乙"),
                ([0, 76, 100, 86], "C. 丙"),
                ([0, 88, 100, 98], "D. 丁"),
            ],
        )

        questions = split_questions([page])

        self.assertEqual(len(questions), 1)
        self.assertNotIn("方法技巧", questions[0].text)
        self.assertNotIn("第一章", questions[0].text)


if __name__ == "__main__":
    unittest.main()
