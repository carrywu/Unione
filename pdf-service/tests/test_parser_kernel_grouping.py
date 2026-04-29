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


class ParserKernelGroupingTest(unittest.TestCase):
    def test_following_material_is_not_absorbed_into_previous_question(self):
        page = make_page(
            1,
            "1. 第一题题干\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"
            "2. 第二题题干\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"
            "根据以下资料，回答3-5题\n2024年全市工业产值增长。\n"
            "3. 第三题题干\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n",
            [
                ([0, 0, 100, 10], "1. 第一题题干"),
                ([0, 12, 100, 22], "A. 甲"),
                ([0, 24, 100, 34], "B. 乙"),
                ([0, 36, 100, 46], "C. 丙"),
                ([0, 48, 100, 58], "D. 丁"),
                ([0, 80, 100, 90], "2. 第二题题干"),
                ([0, 92, 100, 102], "A. 甲"),
                ([0, 104, 100, 114], "B. 乙"),
                ([0, 116, 100, 126], "C. 丙"),
                ([0, 128, 100, 138], "D. 丁"),
                ([0, 160, 180, 170], "根据以下资料，回答3-5题"),
                ([0, 172, 180, 182], "2024年全市工业产值增长。"),
                ([0, 200, 100, 210], "3. 第三题题干"),
                ([0, 212, 100, 222], "A. 甲"),
                ([0, 224, 100, 234], "B. 乙"),
                ([0, 236, 100, 246], "C. 丙"),
                ([0, 248, 100, 258], "D. 丁"),
            ],
        )

        questions = split_questions([page])

        self.assertEqual(len(questions), 3)
        self.assertNotIn("根据以下资料", questions[1].text)
        self.assertIsNotNone(questions[2].material_id)
        self.assertIsNone(questions[1].material_id)


if __name__ == "__main__":
    unittest.main()
