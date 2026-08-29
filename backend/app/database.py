from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_runtime_schema() -> None:
    """Keep existing local demo databases usable after additive MVP upgrades."""
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "exams" in inspector.get_table_names():
            exam_columns = {column["name"] for column in inspector.get_columns("exams")}
            if "ai_summary" not in exam_columns:
                connection.execute(text("ALTER TABLE exams ADD COLUMN ai_summary VARCHAR(500) NOT NULL DEFAULT ''"))
            if "exam_time" not in exam_columns:
                connection.execute(text("ALTER TABLE exams ADD COLUMN exam_time VARCHAR(5) NOT NULL DEFAULT '09:00'"))
            if "priority_chapters" not in exam_columns:
                connection.execute(text("ALTER TABLE exams ADD COLUMN priority_chapters TEXT NOT NULL DEFAULT ''"))
            if "planning_preferences" not in exam_columns:
                connection.execute(text("ALTER TABLE exams ADD COLUMN planning_preferences TEXT NOT NULL DEFAULT ''"))
            if "last_replan_summary" not in exam_columns:
                connection.execute(text("ALTER TABLE exams ADD COLUMN last_replan_summary VARCHAR(700) NOT NULL DEFAULT ''"))
            if "pace_advice" not in exam_columns:
                connection.execute(text("ALTER TABLE exams ADD COLUMN pace_advice VARCHAR(700) NOT NULL DEFAULT ''"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_exams_exam_date_time ON exams (exam_date, exam_time)"))
        if "study_tasks" in inspector.get_table_names():
            task_columns = {column["name"] for column in inspector.get_columns("study_tasks")}
            if "suggested_start_time" not in task_columns:
                connection.execute(text("ALTER TABLE study_tasks ADD COLUMN suggested_start_time VARCHAR(5) NOT NULL DEFAULT '19:00'"))
            if "suggested_end_time" not in task_columns:
                connection.execute(text("ALTER TABLE study_tasks ADD COLUMN suggested_end_time VARCHAR(5) NOT NULL DEFAULT '20:00'"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_study_tasks_date_time ON study_tasks (study_date, suggested_start_time)"))
        connection.execute(text("PRAGMA optimize"))
