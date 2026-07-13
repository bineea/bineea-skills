import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill", ROOT / "scripts" / "backfill_failure_samples.py"
)
backfill = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = backfill
SPEC.loader.exec_module(backfill)


def make_attempt(
    *,
    source_file="run/prediction.json",
    prediction_id="2026-07-06_BJT_MEX_ENG",
    prediction_date="2026-07-06",
    team_a="Mexico",
    team_b="England",
    primary=(0, 0),
    alternatives=None,
    tails=None,
    favorite_side="team_b",
    mtime=1.0,
    strict=False,
):
    alternatives = alternatives or []
    tails = tails or []
    return backfill.PredictionAttempt(
        source_file=source_file,
        absolute_path=Path(source_file),
        source_mtime=mtime,
        prediction_id=prediction_id,
        prediction_date=prediction_date,
        team_a=team_a,
        team_b=team_b,
        primary_score=primary,
        primary_score_text=backfill.score_text(primary),
        alternative_scores=alternatives,
        tail_scores=tails,
        final_prediction={
            "primary_score": backfill.score_text(primary),
            "total_goals_min": 0,
            "total_goals_max": 2,
            "both_teams_to_score": "low",
            "strong_third_goal": "low",
            "weak_second_goal": "low",
            "score_orientation": {"favorite_side": favorite_side},
        },
        completeness_score=20,
        strict_version=strict,
    )


class BackfillFailureSampleTests(unittest.TestCase):
    def test_bjt_prediction_matches_previous_day_americas_fixture(self):
        attempt = make_attempt(
            prediction_id="2026-07-06_BJT_BRA_NOR",
            prediction_date="2026-07-06",
            team_a="Brazil",
            team_b="Norway",
            primary=(2, 1),
            favorite_side="team_a",
        )
        result = backfill.MatchResult(
            match_id="2026-07-05_BRA_NOR",
            match_date="2026-07-05",
            team_a="Brazil",
            team_b="Norway",
            actual_score=(1, 2),
        )

        matched = backfill.match_prediction_to_actual(attempt, [result])

        self.assertIsNotNone(matched)
        self.assertEqual("2026-07-05_BRA_NOR", matched.match_id)

    def test_duplicate_versions_select_strict_as_canonical(self):
        result = backfill.MatchResult(
            match_id="2026-07-05_BRA_NOR",
            match_date="2026-07-05",
            team_a="Brazil",
            team_b="Norway",
            actual_score=(1, 2),
        )
        loose = make_attempt(source_file="normal/BRA_NOR.json", mtime=10.0, strict=False)
        strict = make_attempt(source_file="strict/BRA_NOR.json", mtime=1.0, strict=True)
        loose.matched_result = result
        strict.matched_result = result

        selected = backfill.select_canonical_attempts([loose, strict])

        self.assertIs(selected["2026-07-05_BRA_NOR"], strict)

    def test_open_actual_score_tags_low_score_lock_and_second_goals(self):
        attempt = make_attempt(
            primary=(0, 0),
            team_a="Mexico",
            team_b="England",
            favorite_side="team_b",
        )
        actual = backfill.MatchResult(
            match_id="2026-07-05_MEX_ENG",
            match_date="2026-07-05",
            team_a="Mexico",
            team_b="England",
            actual_score=(2, 3),
        )

        tags, _, _ = backfill.classify_failure(attempt, actual)

        self.assertIn("过度锁定低比分", tags)
        self.assertIn("低估强队第三球", tags)
        self.assertIn("低估弱队第二球", tags)

    def test_actual_score_in_tail_but_not_main_or_alternative_is_tagged(self):
        attempt = make_attempt(
            primary=(1, 0),
            alternatives=[(2, 0)],
            tails=[(1, 1)],
            favorite_side="team_a",
        )
        actual = backfill.MatchResult(
            match_id="2026-06-19_CZE_RSA",
            match_date="2026-06-19",
            team_a="Czechia",
            team_b="South Africa",
            actual_score=(1, 1),
        )

        tags, _, _ = backfill.classify_failure(attempt, actual)

        self.assertIn("尾部未进入主次", tags)


if __name__ == "__main__":
    unittest.main()
