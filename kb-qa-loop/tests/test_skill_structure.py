import os
import re
import unittest


SKILL_MD_PATH = r"C:\Users\guowb1\.claude\skills\kb-qa-loop\SKILL.md"


class TestSkillStructure(unittest.TestCase):
    def test_skill_md_exists(self):
        self.assertTrue(os.path.exists(SKILL_MD_PATH), f"SKILL.md 不存在: {SKILL_MD_PATH}")

    def test_skill_md_frontmatter_has_name_and_description(self):
        with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # very small frontmatter validator
        m = re.search(r"^---\s*\n([\s\S]*?)\n---\s*\n", content)
        self.assertIsNotNone(m, "SKILL.md 缺少 frontmatter（以 --- 包裹）")
        fm = m.group(1)
        self.assertRegex(fm, r"(?m)^name:\s*.+$", "frontmatter 缺少 name 字段")
        self.assertRegex(fm, r"(?m)^description:\s*.+$", "frontmatter 缺少 description 字段")

    def test_skill_md_mentions_required_resources(self):
        with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("vector_retrieval.py", content)
        self.assertIn("prompts/kb_judge_sufficiency.md", content)
        self.assertIn("prompts/kb_answer_with_citations.md", content)

    def test_skill_md_mentions_hard_stops(self):
        with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("max_turns", content)
        self.assertIn("max_elapsed_seconds", content)


if __name__ == "__main__":
    unittest.main()
