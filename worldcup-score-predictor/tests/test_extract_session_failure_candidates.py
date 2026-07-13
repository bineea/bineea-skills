import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extractor", ROOT / "scripts" / "extract_session_failure_candidates.py"
)
extractor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(extractor)


class SessionFailureCandidateExtractionTests(unittest.TestCase):
    def write_session(self, codex_home: Path, session_id: str, text: str, role: str = "assistant") -> None:
        (codex_home / "sessions").mkdir(exist_ok=True)
        session_file = codex_home / "sessions" / f"rollout-test-{session_id}.jsonl"
        payload = {
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "output_text", "text": text}],
            },
        }
        session_file.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_extracts_candidates_without_importing_to_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-1111-7222-8333-944455556666"
            (codex_home / "session_index.jsonl").write_text(
                json.dumps(
                    {"id": session_id, "thread_name": "世界杯预测线程"},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.write_session(
                codex_home,
                session_id,
                "世界杯比分预测：巴西 vs 挪威，首选比分 2-1，次选比分 1-1。",
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual(1, len(candidates))
            self.assertEqual("needs_review", candidates[0]["status"])
            self.assertEqual("世界杯预测线程", candidates[0]["thread_name"])
            self.assertIn("2-1", candidates[0]["candidate_scores"])
            self.assertFalse((codex_home / "worldcup_prediction_knowledge.sqlite").exists())

    def test_extract_scores_ignores_date_like_fragments(self):
        scores = extractor.extract_scores("北京时间07-06，首选比分 1-1，实际比分 2-3。")

        self.assertEqual(["1-1", "2-3"], scores)

    def test_ignores_implementation_plan_noise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-2222-7333-8444-955566667777"
            self.write_session(
                codex_home,
                session_id,
                (
                    "PLEASE IMPLEMENT THIS PLAN: # 补旧失败数据\n"
                    "## Key Changes\n"
                    "- 同一比赛多版本预测去重。\n"
                    "- 0-0/1-1 预测遇到 2-3 实际比分时打标签。"
                ),
                role="user",
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual([], candidates)

    def test_ignores_structured_agent_patch_noise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-3333-7444-8555-966677778888"
            self.write_session(
                codex_home,
                session_id,
                (
                    '{ "schema_version": "role-result-1.0", "role_id": "market_history_agent", '
                    '"coverage": {"completed_dimension_keys": ["market_odds"]}, '
                    '"results": [{"match": {"team_a": "巴西", "team_b": "挪威"}, '
                    '"scores": ["2-1", "1-1"]}] }'
                ),
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual([], candidates)

    def test_ignores_generic_methodology_examples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-4444-7555-8666-977788889999"
            self.write_session(
                codex_home,
                session_id,
                (
                    "预测世界杯足球比分，建议从球队实力和战术匹配分析。"
                    "例如强队面对低位防守可能是 1-0、2-0 或 1-1，"
                    "开放比赛可能是 2-1、3-2。"
                ),
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual([], candidates)

    def test_extracts_post_match_review_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-5555-7666-8777-988899990000"
            self.write_session(
                codex_home,
                session_id,
                (
                    "这场赛后看，我之前把主预测放在 2-1，实际比分是 1-1，"
                    "错在高估比利时第二球。"
                ),
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual(1, len(candidates))
            self.assertIn("2-1", candidates[0]["candidate_scores"])
            self.assertIn("1-1", candidates[0]["candidate_scores"])

    def test_ignores_soft_dimension_methodology(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-6666-7777-8888-999900001111"
            self.write_session(
                codex_home,
                session_id,
                (
                    "可以增加，而且这是一个很有价值但要谨慎使用的软信息维度。"
                    "例如：原预测强队 2-0，若关系紧张可修正为 1-0 或 1-1。"
                ),
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual([], candidates)

    def test_url_fragments_are_not_match_text(self):
        match_text = extractor.extract_match_text(
            "https://example.com/belgium-vs-egypt-prediction-world-cup-report"
        )

        self.assertEqual("", match_text)

    def test_ignores_completed_update_summary_without_prediction_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            session_id = "019f32aa-7777-7888-8999-900011112222"
            self.write_session(
                codex_home,
                session_id,
                (
                    "已更新完成。北京时间 07-06 对应两场世界杯比赛已写入。"
                    "新增比赛：巴西 1-2 挪威，墨西哥 2-3 英格兰。"
                ),
            )

            candidates = extractor.extract_candidates(codex_home)

            self.assertEqual([], candidates)


if __name__ == "__main__":
    unittest.main()
