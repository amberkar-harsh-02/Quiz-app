import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# main.py refuses to import without a SECRET_KEY, so set one before anything imports it
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Swap the real SQLite file for a shared in-memory database BEFORE main is imported,
# so main's create_all() and every SessionLocal() call hit the test database
import database

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.engine = test_engine
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

import models  # noqa: E402
import main  # noqa: E402
from game_manager import manager  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state():
    """Fresh tables and an empty room registry for every test."""
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    manager.active_rooms.clear()
    yield
    manager.active_rooms.clear()


@pytest.fixture
def db():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # Entering the context gives all websockets one shared event loop, so the host's
    # broadcasts can reach student sockets opened on the same client
    with TestClient(main.app) as c:
        yield c


def make_user(db, email, is_professor=False, password="password123"):
    user = models.User(
        email=email,
        hashed_password=main.get_password_hash(password),
        is_professor=is_professor,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_header(user):
    token = main.create_access_token({"sub": user.email, "is_professor": user.is_professor})
    return {"Authorization": f"Bearer {token}"}


def make_quiz(db, owner, title="Sample Quiz", questions=None):
    quiz = models.Quiz(title=title, owner_id=owner.id)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    for q in questions or []:
        db.add(models.Question(quiz_id=quiz.id, **q))
    db.commit()
    db.refresh(quiz)
    return quiz


def question_data(text="2 + 2?", correct="blue", time_limit=20, explanation="Basic math"):
    return {
        "text": text,
        "option_red": "3",
        "option_blue": "4",
        "option_yellow": "5",
        "option_green": "22",
        "correct_option": correct,
        "time_limit_seconds": time_limit,
        "explanation": explanation,
    }


@pytest.fixture
def professor(db):
    return make_user(db, "prof@csumb.edu", is_professor=True)


@pytest.fixture
def student(db):
    return make_user(db, "student@csumb.edu", is_professor=False)
