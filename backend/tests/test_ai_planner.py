import json
from datetime import date, timedelta

import pytest

from app.ai_planner import AIPlanTask, AIStudyPlan, OpenAIPlannerError, _normalize_plan_ranges, _validate_plan, generate_study_plan


class FakeResponses:
    last_payload = None

    def create(self, **kwargs):
        assert kwargs["text"]["format"]["type"] == "json_schema"
        assert kwargs["reasoning"] == {"effort": "minimal"}
        FakeResponses.last_payload = json.loads(kwargs["input"])
        payload = {
            "summary": "수업을 피해 저녁에 10페이지를 학습합니다.",
            "tasks": [{
                "study_date": date.today().isoformat(),
                "pass_number": 1,
                "scope_start": 1,
                "scope_end": 10,
                "suggested_start_time": "19:00",
                "suggested_end_time": "20:00",
            }],
        }
        return type("Response", (), {"output_text": json.dumps(payload)})()


class FakeOpenAI:
    def __init__(self, **kwargs):
        assert kwargs["api_key"] == "test-key"
        self.responses = FakeResponses()


def test_openai_structured_plan(monkeypatch) -> None:
    monkeypatch.setattr("app.ai_planner.OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.ai_planner.OpenAI", FakeOpenAI)
    plan = generate_study_plan(
        subject="생화학",
        exam_date=date.today() + timedelta(days=2),
        scope_start=1,
        scope_end=10,
        scope_unit="페이지",
        target_passes=1,
        completed_units=0,
        start_date=date.today(),
        events=[],
        planning_preferences="암기 과목이라 짧게 여러 번 보고 싶어요.",
        learning_profile={"confidence": "medium", "sample_size": 4, "average_completion_ratio": 0.8},
    )
    assert plan.tasks[0].suggested_start_time == "19:00"
    assert plan.tasks[0].scope_end == 10
    assert FakeResponses.last_payload["learning_profile"]["average_completion_ratio"] == 0.8
    assert FakeResponses.last_payload["progress"]["required_next_scope_start"] == 1
    assert FakeResponses.last_payload["exam"]["planning_preferences"] == "암기 과목이라 짧게 여러 번 보고 싶어요."


def test_replan_range_gaps_are_normalized_from_completed_progress() -> None:
    today = date.today()
    malformed = AIStudyPlan(summary="개인화 일정", tasks=[
        AIPlanTask(study_date=today, pass_number=1, scope_start=15, scope_end=20, suggested_start_time="19:00", suggested_end_time="20:00"),
        AIPlanTask(study_date=today + timedelta(days=1), pass_number=2, scope_start=3, scope_end=8, suggested_start_time="19:00", suggested_end_time="20:00"),
    ])
    normalized, repaired = _normalize_plan_ranges(
        malformed, today, today + timedelta(days=3), 1, 10,
        completed_units=4, expected_units=16,
    )
    assert repaired is True
    assert [(task.pass_number, task.scope_start, task.scope_end) for task in normalized.tasks] == [
        (1, 5, 10), (2, 1, 2), (2, 3, 10),
    ]
    assert sum(task.scope_end - task.scope_start + 1 for task in normalized.tasks) == 16


def test_chapter_ranges_are_normalized_in_tenths() -> None:
    today = date.today()
    proposed = AIStudyPlan(summary="챕터 분할", tasks=[
        AIPlanTask(study_date=today, pass_number=1, scope_start=1, scope_end=1.9, suggested_start_time="19:00", suggested_end_time="20:00"),
        AIPlanTask(study_date=today + timedelta(days=2), pass_number=1, scope_start=2, scope_end=2.9, suggested_start_time="19:00", suggested_end_time="20:00"),
    ])
    normalized, _ = _normalize_plan_ranges(proposed, today, today + timedelta(days=3), 1, 2.9, 0, 2.0, 0.1)
    assert [(task.scope_start, task.scope_end) for task in normalized.tasks] == [(1.0, 1.9), (2.0, 2.9)]
    _validate_plan(normalized, today, today + timedelta(days=3), 1, 2.9, 0, 2.0, 0.1)


def test_plan_must_use_late_part_of_remaining_period() -> None:
    today = date.today()
    early_only = AIStudyPlan(summary="초반 몰아넣기", tasks=[
        AIPlanTask(study_date=today, pass_number=1, scope_start=1, scope_end=10, suggested_start_time="19:00", suggested_end_time="20:00"),
    ])
    with pytest.raises(OpenAIPlannerError, match="기간 후반"):
        _validate_plan(early_only, today, today + timedelta(days=7), 1, 10, 0, 10, 1.0)
