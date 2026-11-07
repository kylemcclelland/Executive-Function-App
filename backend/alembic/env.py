from logging.config import fileConfig

from alembic import context

from app.core.config import Settings
from app.db import Base, make_engine
from app.models import (  # noqa: F401
    Book,
    CoverLookup,
    CoverServiceState,
    DailyPriority,
    InboxItem,
    Milestone,
    Note,
    NoteLink,
    NoteTag,
    Project,
    ProjectNote,
    ProjectUpdate,
    Step,
    Task,
    User,
    WorkSession,
)

config = context.config
if config.config_file_name is not None:
    # Keep application loggers (e.g. the Open Library diagnostics) alive: fileConfig would
    # otherwise disable every logger that already exists when migrations run at startup.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = Settings()
url = settings.database_url

if context.is_offline_mode():
    context.configure(
        url=url, target_metadata=Base.metadata, literal_binds=True, compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    def run(connection):
        context.configure(
            connection=connection, target_metadata=Base.metadata, compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        run(supplied_connection)
    else:
        engine = make_engine(
            url,
            settings.postgres_password.get_secret_value() if settings.postgres_password else None,
        )
        with engine.connect() as connection:
            run(connection)
        engine.dispose()
