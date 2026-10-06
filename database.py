from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./kahoot.db"

# check_same_thread=False is required to use SQLite securely with FastAPI's async routing
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Enable WAL mode for high concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def add_missing_columns(bind):
    """create_all() never alters existing tables, so add columns introduced after a DB was created."""
    with bind.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(questions)"))}
        if columns and "explanation" not in columns:
            conn.execute(text("ALTER TABLE questions ADD COLUMN explanation TEXT"))

        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(quizzes)"))}
        if columns and "use_timer" not in columns:
            conn.execute(text("ALTER TABLE quizzes ADD COLUMN use_timer BOOLEAN NOT NULL DEFAULT 1"))
        if columns and "auto_advance_results" not in columns:
            conn.execute(text("ALTER TABLE quizzes ADD COLUMN auto_advance_results BOOLEAN NOT NULL DEFAULT 1"))
