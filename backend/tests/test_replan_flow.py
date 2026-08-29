from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app, build_learning_profile
from app.models import Exam, StudyLog, StudyTask


def fake_openai_tasks(db, exam, start_date):
    size = exam.scope_end - exam.scope_start + 1
    completed = sum(log.completed_units for task in exam.tasks for log in task.logs)
    remaining = max(0, int(size * exam.target_passes) - completed)
    if remaining:
        task = StudyTask(
            exam_id=exam.id,
            study_date=start_date,
            pass_number=completed // size + 1,
            scope_start=exam.scope_start + completed % size,
            scope_end=exam.scope_start + completed % size + remaining - 1 if remaining <= size - completed % size else exam.scope_end,
            planned_units=min(remaining, size - completed % size),
            status="PLANNED",
            plan_version=exam.plan_version,
            suggested_start_time="19:00",
            suggested_end_time="20:00",
        )
        db.add(task)
        exam.ai_summary = "테스트용 OpenAI 계획"
        db.flush()
        return 1
    return 0


def test_partial_check_in_creates_new_plan_version(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.main.create_openai_tasks", fake_openai_tasks)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            overview = client.post("/api/demo/reset").json()
            exam = overview["exams"][0]
            task = next(item for item in exam["tasks"] if item["scope_end"] > item["scope_start"])
            actual_end = task["scope_start"]
            response = client.post(
                f"/api/tasks/{task['id']}/check-in",
                json={"result": "PARTIAL", "actual_scope_end": actual_end},
            )
        assert response.status_code == 200
        result = response.json()
        assert result["new_version"] == result["previous_version"] + 1
        assert result["changed_tasks"] > 0
        assert result["exam"]["current_passes"] > 0
        assert any(item["plan_version"] == result["new_version"] for item in result["exam"]["tasks"])
        assert "replan_explanation" in result
        assert "recommendation" in result
        assert result["exam"]["plan_logs"][0]["new_version"] == result["new_version"]
        assert result["exam"]["completion_logs"][0]["completed_units"] == 1
    finally:
        app.dependency_overrides.clear()


def test_exam_can_be_deleted(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.main.create_openai_tasks", fake_openai_tasks)

    def override_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            exam = client.post("/api/demo/reset").json()["exams"][0]
            response = client.delete(f"/api/exams/{exam['id']}")
            overview = client.get("/api/overview").json()
        assert response.status_code == 204
        assert overview["exams"] == []
    finally:
        app.dependency_overrides.clear()


def test_weekly_recurring_event_creates_each_occurrence() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/events/recurring", json={
                "title": "매주 수업", "event_type": "CLASS",
                "start_date": "2026-09-01", "end_date": "2026-09-22",
                "start_time": "10:00", "end_time": "11:30",
            })
            overview = client.get("/api/overview").json()
        assert response.status_code == 201
        assert [event["starts_at"][:10] for event in response.json()] == ["2026-09-01", "2026-09-08", "2026-09-15", "2026-09-22"]
        assert len(overview["events"]) == 4
        assert len({event["recurrence_group_id"] for event in overview["events"]}) == 1
    finally:
        app.dependency_overrides.clear()


def test_recurring_event_can_update_one_and_delete_series() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            events = client.post("/api/events/recurring", json={"title": "수업", "event_type": "CLASS", "start_date": "2026-09-01", "end_date": "2026-09-15", "start_time": "10:00", "end_time": "11:00"}).json()
            changed = client.put(f"/api/events/{events[0]['id']}", json={"title": "휴강 보강", "event_type": "CLASS", "starts_at": "2026-09-01T12:00:00", "ends_at": "2026-09-01T13:00:00", "apply_to": "THIS"})
            client.request("DELETE", f"/api/events/{events[1]['id']}", json={"apply_to": "SERIES"})
            overview = client.get("/api/overview").json()
        assert changed.status_code == 200
        assert changed.json()[0]["title"] == "휴강 보강"
        assert overview["events"] == []
    finally:
        app.dependency_overrides.clear()


def test_learning_profile_uses_check_in_history() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        exam = Exam(subject="생화학", exam_date=date.today(), scope_start=1, scope_end=100)
        db.add(exam)
        db.flush()
        tasks = [
            StudyTask(exam_id=exam.id, study_date=date(2026, 8, 24), pass_number=1, scope_start=1, scope_end=20, planned_units=20, status="COMPLETED", suggested_start_time="19:00", suggested_end_time="20:00"),
            StudyTask(exam_id=exam.id, study_date=date(2026, 8, 26), pass_number=1, scope_start=21, scope_end=40, planned_units=20, status="PARTIAL", suggested_start_time="19:00", suggested_end_time="20:00"),
            StudyTask(exam_id=exam.id, study_date=date(2026, 8, 27), pass_number=1, scope_start=41, scope_end=60, planned_units=20, status="COMPLETED", suggested_start_time="10:00", suggested_end_time="11:00"),
        ]
        db.add_all(tasks)
        db.flush()
        db.add_all([
            StudyLog(task_id=tasks[0].id, result="COMPLETED", completed_units=20),
            StudyLog(task_id=tasks[1].id, result="PARTIAL", completed_units=10),
            StudyLog(task_id=tasks[2].id, result="COMPLETED", completed_units=20),
        ])
        db.flush()
        profile = build_learning_profile(db, "생화학")
    assert profile["confidence"] == "medium"
    assert profile["sample_size"] == 3
    assert profile["average_completion_ratio"] == 0.83
    assert "저녁(18-24)" in profile["strongest_time_windows"]
