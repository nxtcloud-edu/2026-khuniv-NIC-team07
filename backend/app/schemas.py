from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    event_type: Literal["CLASS", "WORK", "APPOINTMENT", "OTHER"] = "OTHER"
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class EventRead(EventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recurrence_group_id: str | None = None


class RecurringEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    event_type: Literal["CLASS", "WORK", "APPOINTMENT", "OTHER"] = "OTHER"
    start_date: date
    end_date: date
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date:
            raise ValueError("반복 종료일은 시작일과 같거나 이후여야 합니다.")
        if self.end_time <= self.start_time:
            raise ValueError("종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class EventTimeUpdate(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class EventUpdate(EventCreate):
    apply_to: Literal["THIS", "SERIES"] = "THIS"


class EventDeleteRequest(BaseModel):
    apply_to: Literal["THIS", "SERIES"] = "THIS"


class ExamCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    exam_date: date
    exam_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    scope_start: float = Field(ge=0)
    scope_end: float = Field(gt=0)
    scope_unit: str = Field(default="페이지", max_length=20)
    target_passes: float = Field(default=1.0, ge=1.0, le=5.0)
    priority_chapters: str = Field(default="", max_length=2000)
    planning_preferences: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_end < self.scope_start:
            raise ValueError("범위 끝은 시작보다 크거나 같아야 합니다.")
        return self


class CheckInCreate(BaseModel):
    result: Literal["COMPLETED", "PARTIAL", "MISSED"]
    actual_scope_end: float | None = None


class TaskTimeUpdate(BaseModel):
    suggested_start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    suggested_end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def validate_times(self):
        start = datetime.strptime(self.suggested_start_time, "%H:%M")
        end = datetime.strptime(self.suggested_end_time, "%H:%M")
        if end <= start:
            raise ValueError("종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exam_id: int
    study_date: date
    pass_number: int
    scope_start: float
    scope_end: float
    planned_units: float
    status: str
    plan_version: int
    suggested_start_time: str
    suggested_end_time: str


class ExamRead(BaseModel):
    id: int
    subject: str
    exam_date: date
    exam_time: str
    scope_start: float
    scope_end: float
    scope_unit: str
    target_passes: float
    current_passes: float
    forecast_passes: float
    plan_version: int
    ai_summary: str
    priority_chapters: str
    planning_preferences: str
    last_replan_summary: str
    pace_advice: str
    tasks: list[TaskRead]
    plan_logs: list["PlanLogRead"] = Field(default_factory=list)
    completion_logs: list["CompletionLogRead"] = Field(default_factory=list)


class PlanLogRead(BaseModel):
    id: int
    previous_version: int
    new_version: int
    explanation: str
    recommendation: str
    created_at: datetime


class CompletionLogRead(BaseModel):
    id: int
    task_id: int
    plan_version: int
    study_date: date
    result: str
    planned_units: float
    completed_units: float
    recorded_at: datetime


class OverviewRead(BaseModel):
    events: list[EventRead]
    exams: list[ExamRead]


class CheckInResponse(BaseModel):
    message: str
    previous_version: int
    new_version: int
    changed_tasks: int
    performance_delta: int
    projected_passes: float
    replan_explanation: str
    recommendation: str
    exam: ExamRead
