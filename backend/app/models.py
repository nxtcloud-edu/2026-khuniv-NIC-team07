from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(30), default="OTHER")
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    recurrence_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(120))
    exam_date: Mapped[date] = mapped_column(Date)
    exam_time: Mapped[str] = mapped_column(String(5), default="09:00")
    scope_start: Mapped[float] = mapped_column(Float)
    scope_end: Mapped[float] = mapped_column(Float)
    scope_unit: Mapped[str] = mapped_column(String(20), default="페이지")
    target_passes: Mapped[float] = mapped_column(Float, default=1.0)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    ai_summary: Mapped[str] = mapped_column(String(500), default="")
    priority_chapters: Mapped[str] = mapped_column(Text, default="")
    planning_preferences: Mapped[str] = mapped_column(Text, default="")
    last_replan_summary: Mapped[str] = mapped_column(String(700), default="")
    pace_advice: Mapped[str] = mapped_column(String(700), default="")
    tasks: Mapped[list["StudyTask"]] = relationship(back_populates="exam", cascade="all, delete-orphan")
    plan_logs: Mapped[list["PlanChangeLog"]] = relationship(back_populates="exam", cascade="all, delete-orphan")


class StudyTask(Base):
    __tablename__ = "study_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"))
    study_date: Mapped[date] = mapped_column(Date)
    pass_number: Mapped[int] = mapped_column(Integer)
    scope_start: Mapped[float] = mapped_column(Float)
    scope_end: Mapped[float] = mapped_column(Float)
    planned_units: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    suggested_start_time: Mapped[str] = mapped_column(String(5), default="19:00")
    suggested_end_time: Mapped[str] = mapped_column(String(5), default="20:00")
    exam: Mapped[Exam] = relationship(back_populates="tasks")
    logs: Mapped[list["StudyLog"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class StudyLog(Base):
    __tablename__ = "study_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("study_tasks.id"))
    result: Mapped[str] = mapped_column(String(20))
    completed_units: Mapped[float] = mapped_column(Float, default=0)
    actual_scope_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    task: Mapped[StudyTask] = relationship(back_populates="logs")


class PlanChangeLog(Base):
    __tablename__ = "plan_change_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    previous_version: Mapped[int] = mapped_column(Integer)
    new_version: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(String(700), default="")
    recommendation: Mapped[str] = mapped_column(String(700), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    exam: Mapped[Exam] = relationship(back_populates="plan_logs")
