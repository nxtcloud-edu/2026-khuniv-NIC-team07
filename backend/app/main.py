from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.ai_planner import OpenAIPlannerError, generate_study_plan
from app.config import OPENAI_API_KEY, OPENAI_MODEL, TIMEZONE
from app.database import Base, SessionLocal, engine, get_db, migrate_runtime_schema
from app.models import CalendarEvent, Exam, PlanChangeLog, StudyLog, StudyTask
from app.schemas import CheckInCreate, CheckInResponse, CompletionLogRead, EventCreate, EventDeleteRequest, EventRead, EventTimeUpdate, EventUpdate, ExamCreate, ExamRead, OverviewRead, PlanLogRead, RecurringEventCreate, TaskRead, TaskTimeUpdate

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_runtime_schema()
    with SessionLocal() as db:
        repair_existing_task_overlaps(db)
    yield


app = FastAPI(title="RE:PLAN Study Planner API", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    return {"status": "ok", "timezone": TIMEZONE, "openai_configured": bool(OPENAI_API_KEY), "openai_model": OPENAI_MODEL}


def scope_quantum(exam: Exam) -> float:
    return 0.1 if exam.scope_unit == "챕터" else 1.0


def scope_size(exam: Exam) -> float:
    return round(exam.scope_end - exam.scope_start + 1, 1)


def completed_units(db: Session, exam_id: int) -> float:
    logs = db.scalars(select(StudyLog).join(StudyTask).where(StudyTask.exam_id == exam_id)).all()
    return sum(log.completed_units for log in logs)


def forecast_passes(db: Session, exam: Exam) -> float:
    done = completed_units(db, exam.id)
    logs = db.scalars(select(StudyLog).join(StudyTask).where(StudyTask.exam_id == exam.id)).all()
    if not logs:
        future = sum(task.planned_units for task in exam.tasks if task.status == "PLANNED")
        return round((done + future) / scope_size(exam), 2)
    logged_days = max(1, len({log.recorded_at.date() for log in logs}))
    daily_rate = done / logged_days
    remaining_days = max(0, (exam.exam_date - date.today()).days - 1)
    return round((done + daily_rate * remaining_days) / scope_size(exam), 2)


def build_learning_profile(db: Session, subject: str) -> dict[str, object]:
    """Summarize stored check-ins without sending raw log rows to OpenAI."""
    rows = db.execute(
        select(StudyLog, StudyTask, Exam)
        .join(StudyTask, StudyLog.task_id == StudyTask.id)
        .join(Exam, StudyTask.exam_id == Exam.id)
        .order_by(StudyLog.recorded_at, StudyLog.id)
    ).all()
    subject_rows = [row for row in rows if row.Exam.subject == subject]
    selected = subject_rows if len(subject_rows) >= 2 else rows
    sample_size = len(selected)
    if sample_size == 0:
        return {"confidence": "none", "sample_size": 0, "subject_sample_size": 0}

    def ratio(row) -> float:
        return row.StudyLog.completed_units / max(1, row.StudyTask.planned_units)

    ratios = [ratio(row) for row in selected]
    recent = ratios[-5:]
    weekday_scores: dict[str, list[float]] = defaultdict(list)
    window_scores: dict[str, list[float]] = defaultdict(list)
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    for row in selected:
        weekday_scores[weekday_names[row.StudyTask.study_date.weekday()]].append(ratio(row))
        hour = int(row.StudyTask.suggested_start_time[:2])
        window = "오전(06-12)" if hour < 12 else "오후(12-18)" if hour < 18 else "저녁(18-24)"
        window_scores[window].append(ratio(row))

    ranked_weekdays = sorted(weekday_scores, key=lambda key: sum(weekday_scores[key]) / len(weekday_scores[key]), reverse=True)
    ranked_windows = sorted(window_scores, key=lambda key: sum(window_scores[key]) / len(window_scores[key]), reverse=True)
    confidence = "high" if sample_size >= 8 else "medium" if sample_size >= 3 else "low"
    return {
        "confidence": confidence,
        "profile_scope": "same_subject" if len(subject_rows) >= 2 else "all_subjects",
        "sample_size": sample_size,
        "subject_sample_size": len(subject_rows),
        "completion_rate": round(sum(row.StudyLog.result == "COMPLETED" for row in selected) / sample_size, 2),
        "average_completion_ratio": round(sum(ratios) / sample_size, 2),
        "recent_completion_ratio": round(sum(recent) / len(recent), 2),
        "average_completed_units": round(sum(row.StudyLog.completed_units for row in selected) / sample_size, 1),
        "strongest_weekdays": ranked_weekdays[:2],
        "strongest_time_windows": ranked_windows[:2],
    }


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in occupied)


def _find_slot(preferred: int, duration: int, occupied: list[tuple[int, int]]) -> tuple[int, int]:
    duration = max(30, min(duration, 240))
    for candidate in list(range(max(360, preferred), 1441 - duration, 15)) + list(range(360, max(360, preferred), 15)):
        if not _overlaps(candidate, candidate + duration, occupied):
            return candidate, candidate + duration
    raise OpenAIPlannerError("해당 날짜에 겹치지 않는 학습 시간을 찾을 수 없습니다. 고정 일정을 조정해 주세요.")


def repair_existing_task_overlaps(db: Session) -> None:
    """Move legacy overlapping study blocks into the nearest free slot."""
    occupied_by_day: dict[date, list[tuple[int, int]]] = {}
    for event in db.scalars(select(CalendarEvent)).all():
        occupied_by_day.setdefault(event.starts_at.date(), []).append((event.starts_at.hour * 60 + event.starts_at.minute, event.ends_at.hour * 60 + event.ends_at.minute))
    changed = False
    tasks = db.scalars(select(StudyTask).where(StudyTask.status == "PLANNED").order_by(StudyTask.study_date, StudyTask.suggested_start_time, StudyTask.id)).all()
    for task in tasks:
        occupied = occupied_by_day.setdefault(task.study_date, [])
        start, end = _minutes(task.suggested_start_time), _minutes(task.suggested_end_time)
        if _overlaps(start, end, occupied):
            try:
                start, end = _find_slot(start, end - start, occupied)
            except OpenAIPlannerError:
                continue
            task.suggested_start_time, task.suggested_end_time = _clock(start), _clock(end)
            changed = True
        occupied.append((start, end))
    if changed:
        db.commit()


def create_openai_tasks(db: Session, exam: Exam, start_date: date) -> int:
    events = db.scalars(select(CalendarEvent).where(CalendarEvent.starts_at < datetime.combine(exam.exam_date, datetime.min.time()))).all()
    other_tasks = db.scalars(select(StudyTask).where(StudyTask.status == "PLANNED", StudyTask.exam_id != exam.id)).all()
    blocking = [{"title": event.title, "starts_at": event.starts_at.isoformat(), "ends_at": event.ends_at.isoformat()} for event in events]
    blocking.extend({"title": "다른 시험 학습 계획", "starts_at": f"{task.study_date.isoformat()}T{task.suggested_start_time}:00", "ends_at": f"{task.study_date.isoformat()}T{task.suggested_end_time}:00"} for task in other_tasks)
    profile = build_learning_profile(db, exam.subject)
    combined_preferences = "\n".join(part for part in [exam.priority_chapters.strip(), exam.planning_preferences.strip()] if part)
    planner_scope_end = exam.scope_end + (0.9 if scope_quantum(exam) == 0.1 else 0)
    plan = generate_study_plan(
        subject=exam.subject,
        exam_date=exam.exam_date,
        scope_start=exam.scope_start,
        scope_end=planner_scope_end,
        scope_unit=exam.scope_unit,
        target_passes=exam.target_passes,
        completed_units=completed_units(db, exam.id),
        start_date=start_date,
        events=blocking,
        planning_preferences=combined_preferences,
        learning_profile=profile,
    )
    if profile["sample_size"]:
        window = (profile.get("strongest_time_windows") or ["아직 확인 중"])[0]
        exam.ai_summary = f"{plan.summary} (실제 기록 {profile['sample_size']}회, 수행 비율 {profile['average_completion_ratio']}, 선호 시간대 {window} 반영)"
    else:
        exam.ai_summary = plan.summary
    occupied_by_day: dict[date, list[tuple[int, int]]] = {}
    for event in events:
        occupied_by_day.setdefault(event.starts_at.date(), []).append((event.starts_at.hour * 60 + event.starts_at.minute, event.ends_at.hour * 60 + event.ends_at.minute))
    for task in other_tasks:
        occupied_by_day.setdefault(task.study_date, []).append((_minutes(task.suggested_start_time), _minutes(task.suggested_end_time)))
    for item in plan.tasks:
        occupied = occupied_by_day.setdefault(item.study_date, [])
        preferred = _minutes(item.suggested_start_time)
        start, end = _find_slot(preferred, _minutes(item.suggested_end_time) - preferred, occupied)
        occupied.append((start, end))
        db.add(StudyTask(
            exam_id=exam.id,
            study_date=item.study_date,
            pass_number=item.pass_number,
            scope_start=item.scope_start,
            scope_end=item.scope_end,
            planned_units=round(item.scope_end - item.scope_start + scope_quantum(exam), 1),
            status="PLANNED",
            plan_version=exam.plan_version,
            suggested_start_time=_clock(start),
            suggested_end_time=_clock(end),
        ))
    db.flush()
    return len(plan.tasks)


def serialize_exam(db: Session, exam: Exam) -> ExamRead:
    done = completed_units(db, exam.id)
    log_rows = db.execute(select(StudyLog, StudyTask).join(StudyTask).where(StudyTask.exam_id == exam.id).order_by(StudyLog.recorded_at)).all()
    plan_logs = db.scalars(select(PlanChangeLog).where(PlanChangeLog.exam_id == exam.id).order_by(PlanChangeLog.created_at.desc())).all()
    return ExamRead(id=exam.id, subject=exam.subject, exam_date=exam.exam_date, exam_time=exam.exam_time, scope_start=exam.scope_start, scope_end=exam.scope_end, scope_unit=exam.scope_unit, target_passes=exam.target_passes, current_passes=round(done / scope_size(exam), 2), forecast_passes=forecast_passes(db, exam), plan_version=exam.plan_version, ai_summary=exam.ai_summary, priority_chapters=exam.priority_chapters, planning_preferences=exam.planning_preferences, last_replan_summary=exam.last_replan_summary, pace_advice=exam.pace_advice, tasks=[TaskRead.model_validate(task) for task in sorted(exam.tasks, key=lambda item: (item.study_date, item.suggested_start_time, item.id))], plan_logs=[PlanLogRead.model_validate(log, from_attributes=True) for log in plan_logs], completion_logs=[CompletionLogRead(id=log.id, task_id=task.id, plan_version=task.plan_version, study_date=task.study_date, result=log.result, planned_units=task.planned_units, completed_units=log.completed_units, recorded_at=log.recorded_at) for log, task in log_rows])


@app.get("/api/overview", response_model=OverviewRead)
def get_overview(db: Session = Depends(get_db)) -> OverviewRead:
    events = db.scalars(select(CalendarEvent).order_by(CalendarEvent.starts_at)).all()
    exams = db.scalars(select(Exam).options(selectinload(Exam.tasks)).order_by(Exam.exam_date)).all()
    return OverviewRead(events=[EventRead.model_validate(event) for event in events], exams=[serialize_exam(db, exam) for exam in exams])


@app.post("/api/events", response_model=EventRead, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> EventRead:
    event = CalendarEvent(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return EventRead.model_validate(event)


@app.post("/api/events/recurring", response_model=list[EventRead], status_code=201)
def create_recurring_event(payload: RecurringEventCreate, db: Session = Depends(get_db)) -> list[EventRead]:
    events: list[CalendarEvent] = []
    group_id = str(uuid4())
    occurrence_date = payload.start_date
    while occurrence_date <= payload.end_date:
        event = CalendarEvent(
            title=payload.title,
            event_type=payload.event_type,
            starts_at=datetime.combine(occurrence_date, payload.start_time),
            ends_at=datetime.combine(occurrence_date, payload.end_time),
            recurrence_group_id=group_id,
        )
        db.add(event)
        events.append(event)
        occurrence_date += timedelta(days=7)
    db.commit()
    for event in events:
        db.refresh(event)
    return [EventRead.model_validate(event) for event in events]


@app.patch("/api/events/{event_id}/time", response_model=EventRead)
def update_event_time(event_id: int, payload: EventTimeUpdate, db: Session = Depends(get_db)) -> EventRead:
    event = db.get(CalendarEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    event.starts_at, event.ends_at = payload.starts_at, payload.ends_at
    db.commit(); db.refresh(event)
    return EventRead.model_validate(event)


@app.put("/api/events/{event_id}", response_model=list[EventRead])
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)) -> list[EventRead]:
    event = db.get(CalendarEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    targets = [event]
    if payload.apply_to == "SERIES" and event.recurrence_group_id:
        targets = db.scalars(select(CalendarEvent).where(CalendarEvent.recurrence_group_id == event.recurrence_group_id)).all()
    start_delta = payload.starts_at - event.starts_at
    end_delta = payload.ends_at - event.ends_at
    for target in targets:
        target.title = payload.title
        target.event_type = payload.event_type
        if payload.apply_to == "SERIES" and event.recurrence_group_id:
            target.starts_at += start_delta
            target.ends_at += end_delta
        else:
            target.starts_at, target.ends_at = payload.starts_at, payload.ends_at
    db.commit()
    return [EventRead.model_validate(target) for target in targets]


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event(event_id: int, payload: EventDeleteRequest | None = None, db: Session = Depends(get_db)) -> None:
    event = db.get(CalendarEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    apply_to = payload.apply_to if payload else "THIS"
    if apply_to == "SERIES" and event.recurrence_group_id:
        db.execute(delete(CalendarEvent).where(CalendarEvent.recurrence_group_id == event.recurrence_group_id))
    else:
        db.delete(event)
    db.commit()


@app.post("/api/exams", response_model=ExamRead, status_code=201)
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)) -> ExamRead:
    if payload.exam_date <= date.today():
        raise HTTPException(status_code=422, detail="시험일은 오늘 이후여야 합니다.")
    exam = Exam(**payload.model_dump())
    db.add(exam)
    db.flush()
    try:
        create_openai_tasks(db, exam, date.today())
    except OpenAIPlannerError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    exam = db.scalar(select(Exam).where(Exam.id == exam.id).options(selectinload(Exam.tasks)))
    assert exam is not None
    return serialize_exam(db, exam)


@app.delete("/api/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: int, db: Session = Depends(get_db)) -> None:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="시험을 찾을 수 없습니다.")
    db.delete(exam); db.commit()


@app.patch("/api/tasks/{task_id}/time", response_model=TaskRead)
def update_task_time(task_id: int, payload: TaskTimeUpdate, db: Session = Depends(get_db)) -> TaskRead:
    task = db.get(StudyTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="공부 계획을 찾을 수 없습니다.")
    start, end = _minutes(payload.suggested_start_time), _minutes(payload.suggested_end_time)
    conflicts = db.scalars(select(StudyTask).where(StudyTask.study_date == task.study_date, StudyTask.status == "PLANNED", StudyTask.id != task.id)).all()
    occupied = [(_minutes(item.suggested_start_time), _minutes(item.suggested_end_time)) for item in conflicts]
    events = db.scalars(select(CalendarEvent).where(CalendarEvent.starts_at < datetime.combine(task.study_date + timedelta(days=1), time.min), CalendarEvent.ends_at > datetime.combine(task.study_date, time.min))).all()
    occupied.extend((event.starts_at.hour * 60 + event.starts_at.minute, event.ends_at.hour * 60 + event.ends_at.minute) for event in events)
    if _overlaps(start, end, occupied):
        raise HTTPException(status_code=409, detail="다른 일정과 시간이 겹칩니다. 빈 시간대로 옮겨 주세요.")
    task.suggested_start_time, task.suggested_end_time = payload.suggested_start_time, payload.suggested_end_time
    db.commit(); db.refresh(task)
    return TaskRead.model_validate(task)


@app.post("/api/tasks/{task_id}/check-in", response_model=CheckInResponse)
def check_in(task_id: int, payload: CheckInCreate, db: Session = Depends(get_db)) -> CheckInResponse:
    task = db.scalar(select(StudyTask).where(StudyTask.id == task_id).options(selectinload(StudyTask.exam)))
    if task is None:
        raise HTTPException(status_code=404, detail="공부 계획을 찾을 수 없습니다.")
    if task.status != "PLANNED":
        raise HTTPException(status_code=409, detail="이미 체크인한 계획입니다.")
    if payload.result == "COMPLETED":
        if payload.actual_scope_end is not None:
            if not task.scope_start <= payload.actual_scope_end <= exam_scope_end(task):
                raise HTTPException(status_code=422, detail="실제 완료 지점은 현재 회독의 시험 범위 안이어야 합니다.")
            actual_end = payload.actual_scope_end
            units = round(actual_end - task.scope_start + scope_quantum(task.exam), 1)
        else:
            units, actual_end = task.planned_units, task.scope_end
    elif payload.result == "MISSED":
        units, actual_end = 0, None
    else:
        if payload.actual_scope_end is None or not task.scope_start <= payload.actual_scope_end < task.scope_end:
            raise HTTPException(status_code=422, detail="일부 완료 지점은 계획 범위 안에 있어야 합니다.")
        units, actual_end = round(payload.actual_scope_end - task.scope_start + scope_quantum(task.exam), 1), payload.actual_scope_end
    task.status = payload.result
    db.add(StudyLog(task_id=task.id, result=payload.result, completed_units=units, actual_scope_end=actual_end))
    db.flush()
    exam, previous_version = task.exam, task.exam.plan_version
    performance_delta = units - task.planned_units
    future_ids = db.scalars(select(StudyTask.id).where(StudyTask.exam_id == exam.id, StudyTask.status == "PLANNED", StudyTask.id != task.id)).all()
    if future_ids:
        db.execute(delete(StudyTask).where(StudyTask.id.in_(future_ids)))
    exam.plan_version += 1
    try:
        changed = create_openai_tasks(db, exam, max(date.today(), task.study_date) + timedelta(days=1))
    except OpenAIPlannerError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    projected = forecast_passes(db, exam)
    if performance_delta > 0:
        explanation = f"예정보다 {performance_delta}{exam.scope_unit} 더 학습해 이후 분량을 줄여 다시 배분했습니다."
    elif performance_delta < 0:
        explanation = f"예정보다 {-performance_delta}{exam.scope_unit} 덜 학습해 남은 기간에 분량을 다시 배분했습니다."
    else:
        explanation = "예정한 분량을 완료해 현재 진도에 맞춰 이후 일정을 다시 정렬했습니다."
    if projected + 0.01 < exam.target_passes:
        advice = f"현재 속도라면 약 {projected}회독이 예상되어 목표 {exam.target_passes}회독에 부족합니다. 하루 공부 강도를 높이거나 목표 회독을 조정해 보세요."
    else:
        advice = f"현재 속도라면 약 {projected}회독이 예상되어 목표 {exam.target_passes}회독을 유지해도 좋습니다."
    exam.last_replan_summary, exam.pace_advice = explanation, advice
    db.add(PlanChangeLog(exam_id=exam.id, previous_version=previous_version, new_version=exam.plan_version, explanation=explanation, recommendation=advice))
    db.commit()
    refreshed = db.scalar(select(Exam).where(Exam.id == exam.id).options(selectinload(Exam.tasks)))
    assert refreshed is not None
    return CheckInResponse(message="실제 수행량을 반영해 남은 계획을 다시 배분했습니다.", previous_version=previous_version, new_version=refreshed.plan_version, changed_tasks=changed, performance_delta=performance_delta, projected_passes=projected, replan_explanation=explanation, recommendation=advice, exam=serialize_exam(db, refreshed))


def exam_scope_end(task: StudyTask) -> float:
    return task.exam.scope_end + (0.9 if scope_quantum(task.exam) == 0.1 else 0)


@app.post("/api/demo/reset", response_model=OverviewRead)
def reset_demo(db: Session = Depends(get_db)) -> OverviewRead:
    db.execute(delete(StudyLog)); db.execute(delete(StudyTask)); db.execute(delete(PlanChangeLog)); db.execute(delete(Exam)); db.execute(delete(CalendarEvent))
    today = date.today()
    db.add_all([
        CalendarEvent(title="전공 수업", event_type="CLASS", starts_at=datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(hour=10), ends_at=datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(hour=15)),
        CalendarEvent(title="카페 아르바이트", event_type="WORK", starts_at=datetime.combine(today + timedelta(days=3), datetime.min.time()).replace(hour=14), ends_at=datetime.combine(today + timedelta(days=3), datetime.min.time()).replace(hour=20)),
    ])
    exam = Exam(subject="생화학", exam_date=today + timedelta(days=8), scope_start=1, scope_end=160, scope_unit="페이지", target_passes=2)
    db.add(exam); db.flush()
    try:
        create_openai_tasks(db, exam, today)
    except OpenAIPlannerError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return get_overview(db)
