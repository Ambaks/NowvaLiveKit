"""
Tests for AssessmentLogger rep correlation across assessment rounds.

The pipeline restarts rep numbering at 1 every assessment round, while
the logger keeps a monotonic sequence — diagnosis messages must attach
to the latest matching rep, not the first round's.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.services.assessment_logger import AssessmentLogger


def _rep_complete_msg(rep_number, is_clean=True):
    return {
        "type": "rep_complete",
        "rep_number": rep_number,
        "max_depth_angle": 100.0,
        "is_clean": is_clean,
        "descent_time_s": 1.2,
        "ascent_time_s": 0.9,
        "faults_detailed": [],
    }


def _make_logger(tmp_path):
    return AssessmentLogger(
        session_dir=tmp_path,
        session_id="test-session",
        user_height_cm=180.0,
    )


class TestNonClobberingLogFiles:
    def test_second_logger_in_same_session_keeps_first_log(self, tmp_path):
        first = _make_logger(tmp_path)
        first.on_rep_complete(_rep_complete_msg(1))
        first.finalize(passed=True)

        second = _make_logger(tmp_path)
        second.finalize(passed=False)

        import json
        first_log = json.loads((tmp_path / "assessment" / "assessment_log.json").read_text())
        second_log = json.loads((tmp_path / "assessment" / "assessment_log_2.json").read_text())
        assert len(first_log["reps"]) == 1
        assert first_log["passed"] is True
        assert second_log["reps"] == []
        assert second_log["passed"] is False

    def test_second_logger_uses_separate_keypoints_dir(self, tmp_path):
        first = _make_logger(tmp_path)
        first.finalize(passed=False)
        second = _make_logger(tmp_path)

        assert first._keypoints_dir != second._keypoints_dir
        assert second._keypoints_dir.name == "keypoints_2"


class TestRepNumberTranslation:
    def test_sequence_numbers_stay_unique_across_rounds(self, tmp_path):
        logger = _make_logger(tmp_path)

        # Round 1: pipeline reps 1-3, round 2: numbering restarts at 1
        for n in (1, 2, 3):
            logger.on_rep_complete(_rep_complete_msg(n))
        logger.on_rep_complete(_rep_complete_msg(1))

        rep_numbers = [r.rep_number for r in logger._log.reps]
        assert rep_numbers == [1, 2, 3, 4]

    def test_diagnosis_attaches_to_latest_rep_after_round_reset(self, tmp_path):
        logger = _make_logger(tmp_path)

        for n in (1, 2, 3):
            logger.on_rep_complete(_rep_complete_msg(n))
        logger.on_rep_complete(_rep_complete_msg(1))

        logger.on_rep_diagnosis(
            1,
            {"immediate_causes": []},
            rep_score={"composite_score": 0.9},
        )

        # Best rep must be the round-2 rep (logger sequence 4), not round 1's rep 1
        assert logger._log.best_rep_number == 4

    def test_diagnosis_within_single_round_matches_directly(self, tmp_path):
        logger = _make_logger(tmp_path)

        logger.on_rep_complete(_rep_complete_msg(1))
        logger.on_rep_complete(_rep_complete_msg(2))

        logger.on_rep_diagnosis(
            2,
            {"immediate_causes": []},
            rep_score={"composite_score": 0.8},
        )

        assert logger._log.best_rep_number == 2
