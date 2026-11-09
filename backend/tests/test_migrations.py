from datetime import date
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app.models import DailyPriority, Step, Task, User


def test_schema_rename_is_reversible_and_preserves_data(application):
    with application.state.session_factory.begin() as db:
        user = User(id=uuid4(), timezone="UTC")
        db.add(user)
        db.flush()
        task = Task(user_id=user.id, title="Keep this task")
        db.add(task)
        db.flush()
        step = Step(task_id=task.id, title="Keep this step", position=0)
        priority = DailyPriority(
            user_id=user.id, task_id=task.id, priority_date=date(2026, 11, 6), position=0,
        )
        db.add_all([step, priority])
        db.flush()
        step_id, priority_id = step.id, priority.id

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001")
        assert "steps" in inspect(connection).get_table_names()
        assert connection.scalar(text("SELECT title FROM steps")) == "Keep this step"
        assert connection.scalar(text("SELECT COUNT(*) FROM daily_priorities")) == 1
        command.upgrade(config, "head")
        assert "task_steps" in inspect(connection).get_table_names()
        columns = {column["name"] for column in inspect(connection).get_columns("daily_priorities")}
        assert "priority_date" in columns
        assert "date" not in columns
    with application.state.session_factory() as db:
        assert db.get(Step, step_id).title == "Keep this step"
        assert db.get(DailyPriority, priority_id).priority_date == date(2026, 11, 6)
        assert db.scalar(select(Task.title)) == "Keep this task"
