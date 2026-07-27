"""Tests for CoachingService shutdown behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.services.assessment_logger import AssessmentLogger
from agent.services.coaching_service import CoachingService


class TestStopFinalizesAssessment:
    def test_stop_finalizes_active_assessment_log(self, tmp_path):
        service = CoachingService(session=None, state=None)
        service._started = True
        service._assessment_logger = AssessmentLogger(
            session_dir=tmp_path,
            session_id="test_session",
            user_height_cm=180.0,
        )

        asyncio.run(service.stop())

        log = json.loads((tmp_path / "assessment" / "assessment_log.json").read_text())
        assert log["completed_at"] is not None
        assert log["passed"] is False
        assert service._assessment_logger is None

    def test_stop_without_assessment_is_clean(self, tmp_path):
        service = CoachingService(session=None, state=None)
        service._started = True

        asyncio.run(service.stop())

        assert service._assessment_logger is None
        assert not (tmp_path / "assessment").exists()
