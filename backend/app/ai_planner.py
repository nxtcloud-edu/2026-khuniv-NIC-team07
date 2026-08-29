import json
import math
from datetime import date, datetime

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from app.config import OPENAI_API_KEY, OPENAI_MODEL


class AIPlanTask(BaseModel):
    study_date: date
    pass_number: int = Field(ge=1)
    scope_start: int = Field(ge=0)
    scope_end: int = Field(ge=0)
    suggested_start_time: str
    suggested_end_time: str


class AIStudyPlan(BaseModel):
    summary: str
    tasks: list[AIPlanTask]


PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "study_date": {"type": "string", "format": "date"},
                    "pass_number": {"type": "integer", "minimum": 1},
                    "scope_start": {"type": "integer", "minimum": 0},
                    "scope_end": {"type": "integer", "minimum": 0},
                    "suggested_start_time": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$"},
                    "suggested_end_time": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$"},
                },
                "required": ["study_date", "pass_number", "scope_start", "scope_end", "suggested_start_time", "suggested_end_time"],
            },
        },
    },
    "required": ["summary", "tasks"],
}


class OpenAIPlannerError(RuntimeError):
    pass


def generate_study_plan(
    *,
    subject: str,
    exam_date: date,
    scope_start: int,
    scope_end: int,
    scope_unit: str,
    target_passes: float,
    completed_units: int,
    start_date: date,
    events: list[dict[str, str]],
    priority_chapters: str = "",
    planning_preferences: str = "",
    learning_profile: dict[str, object] | None = None,
) -> AIStudyPlan:
    if not OPENAI_API_KEY:
        raise OpenAIPlannerError("OPENAI_API_KEY가 설정되지 않았습니다. backend/.env에 API 키를 입력해 주세요.")

    scope_size = scope_end - scope_start + 1
    target_units = math.ceil(scope_size * target_passes)
    remaining_units = max(0, target_units - completed_units)
    if remaining_units == 0:
        return AIStudyPlan(summary="목표 회독을 완료했습니다.", tasks=[])

    payload = {
        "today": start_date.isoformat(),
        "exam": {
            "subject": subject,
            "exam_date": exam_date.isoformat(),
            "scope_start": scope_start,
            "scope_end": scope_end,
            "scope_unit": scope_unit,
            "target_passes": target_passes,
            "priority_chapters": priority_chapters,
            "planning_preferences": planning_preferences,
        },
        "progress": {
            "completed_units_across_passes": completed_units,
            "remaining_units_across_passes": remaining_units,
            "required_next_pass_number": completed_units // scope_size + 1,
            "required_next_scope_start": scope_start + completed_units % scope_size,
        },
        "blocking_events": events,
        "learning_profile": learning_profile or {"confidence": "none", "sample_size": 0},
    }
    instructions = (
        "당신은 대학생 시험 계획을 만드는 일정 최적화 엔진이다. "
        "시험 당일에는 공부를 배정하지 말고, 고정 일정과 시간이 겹치지 않게 하라. "
        "blocking_events에는 다른 시험의 공부 계획도 포함된다. 어떤 시간도 겹치게 배정하지 마라. "
        "priority_chapters가 있으면 강조된 범위를 앞쪽 날짜와 집중하기 좋은 시간에 우선 배치하라. "
        "planning_preferences는 사용자가 자연어로 직접 작성한 과목 특성 및 계획 요구사항이다. "
        "시험 기간, 목표량, 고정 일정, 범위 연속성 규칙을 위반하지 않는 선에서 날짜별 분량, 반복 빈도, "
        "학습 시간과 복습 배치에 그대로 반영하라. 다른 입력과 충돌하면 필수 제약을 우선하라. "
        "범위를 회독 순서대로 빠짐없이 배정하고 같은 회독 안에서 중복시키지 마라. "
        "고정 일정이 많은 날은 학습량을 줄이고 가능한 시간대를 suggested time으로 제시하라. "
        "learning_profile은 저장된 실제 수행 기록의 요약이다. confidence가 medium 또는 high이면 "
        "완료율, 최근 수행 비율, 잘 수행한 요일과 시간대를 날짜별 분량과 suggested time에 적극 반영하라. "
        "평균 수행 비율이 낮으면 한 번의 분량을 작게 나누고, 높으면 감당 가능한 범위에서 블록 분량을 늘려라. "
        "confidence가 none 또는 low이면 패턴을 확정적으로 가정하지 말고 보조 정보로만 사용하라. "
        "개인화하더라도 남은 목표 총량을 줄이거나 범위를 생략해서는 안 된다. "
        "출력은 제공된 JSON schema를 정확히 따라야 한다."
    )
    try:
        response = OpenAI(api_key=OPENAI_API_KEY).responses.create(
            model=OPENAI_MODEL,
            instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False),
            reasoning={"effort": "minimal"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "study_plan",
                    "strict": True,
                    "schema": PLAN_SCHEMA,
                }
            },
        )
        plan = AIStudyPlan.model_validate_json(response.output_text)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise OpenAIPlannerError("OpenAI가 유효한 계획 형식을 반환하지 않았습니다.") from exc
    except Exception as exc:
        raise OpenAIPlannerError(f"OpenAI API 호출에 실패했습니다: {exc}") from exc

    plan.tasks.sort(key=lambda task: (task.study_date, task.suggested_start_time, task.pass_number, task.scope_start))
    plan, repaired = _normalize_plan_ranges(plan, start_date, exam_date, scope_start, scope_end, completed_units, remaining_units)
    if repaired:
        plan.summary = f"{plan.summary} 범위의 누락·중복은 현재 진도에 맞춰 자동 보정했습니다."
    _validate_plan(plan, start_date, exam_date, scope_start, scope_end, completed_units, remaining_units)
    return plan


def _normalize_plan_ranges(
    plan: AIStudyPlan,
    start_date: date,
    exam_date: date,
    scope_start: int,
    scope_end: int,
    completed_units: int,
    expected_units: int,
) -> tuple[AIStudyPlan, bool]:
    """Keep GPT's schedule and chunk proportions while rebuilding a continuous range sequence."""
    if not plan.tasks:
        raise OpenAIPlannerError("OpenAI 계획에 공부 일정이 없습니다.")
    for task in plan.tasks:
        if not start_date <= task.study_date < exam_date:
            raise OpenAIPlannerError("OpenAI 계획에 시험 기간 밖의 날짜가 포함됐습니다.")
        try:
            start_time = datetime.strptime(task.suggested_start_time, "%H:%M")
            end_time = datetime.strptime(task.suggested_end_time, "%H:%M")
        except ValueError as exc:
            raise OpenAIPlannerError("OpenAI 계획의 시간 형식이 올바르지 않습니다.") from exc
        if end_time <= start_time:
            raise OpenAIPlannerError("OpenAI 계획의 종료 시간이 시작 시간보다 빠릅니다.")

    original = [(task.pass_number, task.scope_start, task.scope_end) for task in plan.tasks]
    source_tasks = plan.tasks[:min(len(plan.tasks), expected_units)]
    weights = [max(1, task.scope_end - task.scope_start + 1) for task in source_tasks]
    allocations: list[int] = []
    remaining = expected_units
    remaining_weight = sum(weights)
    for index, weight in enumerate(weights):
        tasks_left = len(weights) - index - 1
        if tasks_left == 0:
            allocation = remaining
        else:
            allocation = max(1, round(remaining * weight / remaining_weight))
            allocation = min(allocation, remaining - tasks_left)
        allocations.append(allocation)
        remaining -= allocation
        remaining_weight -= weight

    normalized: list[AIPlanTask] = []
    scope_length = scope_end - scope_start + 1
    offset = completed_units
    for source, allocation in zip(source_tasks, allocations):
        units_left = allocation
        while units_left:
            pass_number = offset // scope_length + 1
            next_start = scope_start + offset % scope_length
            units = min(units_left, scope_end - next_start + 1)
            normalized.append(AIPlanTask(
                study_date=source.study_date,
                pass_number=pass_number,
                scope_start=next_start,
                scope_end=next_start + units - 1,
                suggested_start_time=source.suggested_start_time,
                suggested_end_time=source.suggested_end_time,
            ))
            offset += units
            units_left -= units

    repaired = original != [(task.pass_number, task.scope_start, task.scope_end) for task in normalized]
    return AIStudyPlan(summary=plan.summary, tasks=normalized), repaired


def _validate_plan(plan: AIStudyPlan, start_date: date, exam_date: date, scope_start: int, scope_end: int, completed_units: int, expected_units: int) -> None:
    planned_units = 0
    scope_length = scope_end - scope_start + 1
    offset = completed_units
    for task in plan.tasks:
        if not start_date <= task.study_date < exam_date:
            raise OpenAIPlannerError("OpenAI 계획에 시험 기간 밖의 날짜가 포함됐습니다.")
        if not scope_start <= task.scope_start <= task.scope_end <= scope_end:
            raise OpenAIPlannerError("OpenAI 계획에 시험 범위 밖의 학습량이 포함됐습니다.")
        expected_pass = offset // scope_length + 1
        expected_start = scope_start + offset % scope_length
        if task.pass_number != expected_pass or task.scope_start != expected_start:
            raise OpenAIPlannerError("OpenAI 계획의 회독 또는 범위 순서에 누락·중복이 있습니다.")
        start_time = datetime.strptime(task.suggested_start_time, "%H:%M")
        end_time = datetime.strptime(task.suggested_end_time, "%H:%M")
        if end_time <= start_time:
            raise OpenAIPlannerError("OpenAI 계획의 종료 시간이 시작 시간보다 빠릅니다.")
        units = task.scope_end - task.scope_start + 1
        planned_units += units
        offset += units
    if planned_units != expected_units:
        raise OpenAIPlannerError(f"OpenAI 계획량({planned_units})이 남은 목표량({expected_units})과 일치하지 않습니다.")
