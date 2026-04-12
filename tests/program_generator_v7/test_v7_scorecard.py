from scorecard import generate_scorecard


def test_v7_scorecard_runs_for_selected_personas():
    rows = generate_scorecard(["hypertrophy_general", "power_basketball_inseason"])

    assert len(rows) == 2
    for row in rows:
        assert row["v5"]["weeks"] > 0
        assert row["v7"]["weeks"] > 0
        assert row["v7"]["unique_exercises"] > 0
        assert row["v7"]["validation_score"] >= 0
        assert row["v7"]["kg_version"]
        assert row["v7"]["trace_entries"] > 0
