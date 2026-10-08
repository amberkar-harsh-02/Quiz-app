from sqlalchemy import create_engine, text

from database import add_missing_columns


def test_adds_explanation_column_to_old_database_and_keeps_rows():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE questions (id INTEGER PRIMARY KEY, text VARCHAR)"))
        conn.execute(text("INSERT INTO questions (text) VALUES ('Old question')"))

    add_missing_columns(engine)
    add_missing_columns(engine)  # safe to run on every startup

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(questions)"))}
        rows = conn.execute(text("SELECT text, explanation FROM questions")).all()
    assert "explanation" in columns
    assert rows == [("Old question", None)]


def test_adds_use_timer_column_to_old_quizzes_and_defaults_to_on():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE questions (id INTEGER PRIMARY KEY, text VARCHAR)"))
        conn.execute(text("CREATE TABLE quizzes (id INTEGER PRIMARY KEY, title VARCHAR)"))
        conn.execute(text("INSERT INTO quizzes (title) VALUES ('Old quiz')"))

    add_missing_columns(engine)
    add_missing_columns(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT title, use_timer, auto_advance_results, speed_weight FROM quizzes")).all()
        questions = {row[1] for row in conn.execute(text("PRAGMA table_info(questions)"))}
    assert rows == [("Old quiz", 1, 1, 50)]
    assert {"image_id", "image_alt"} <= questions
