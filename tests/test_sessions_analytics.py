import pytest

import models
from conftest import auth_header, make_quiz, make_user, question_data


@pytest.fixture
def played_session(db, professor, student):
    """A finished game: 2 questions, Alice (logged in) got both right, Bob got one right."""
    quiz = make_quiz(db, professor, "Played Quiz", questions=[
        question_data(text="Q1", correct="blue"),
        question_data(text="Q2", correct="red", explanation=None),
    ])
    q1, q2 = quiz.questions
    session = models.GameSession(quiz_id=quiz.id, room_code="ABC123")
    db.add(session)
    db.commit()

    alice = models.StudentResult(session_id=session.id, student_name="Alice", total_score=1800,
                                 correct_answers=2, user_id=student.id)
    bob = models.StudentResult(session_id=session.id, student_name="Bob Smith", total_score=600,
                               correct_answers=1)
    db.add_all([alice, bob])
    db.commit()

    db.add_all([
        models.StudentAnswer(result_id=alice.id, question_id=q1.id, selected_option="blue", is_correct=1),
        models.StudentAnswer(result_id=alice.id, question_id=q2.id, selected_option="red", is_correct=1),
        models.StudentAnswer(result_id=bob.id, question_id=q1.id, selected_option="green", is_correct=0),
        models.StudentAnswer(result_id=bob.id, question_id=q2.id, selected_option="red", is_correct=1),
    ])
    db.commit()
    return {"quiz": quiz, "session": session, "q1": q1, "q2": q2}


# --- GET /receipt ---

def test_receipt_returns_csv(client, played_session):
    sid = played_session["session"].id
    res = client.get(f"/receipt/{sid}/Bob Smith")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "filename=cst315_receipt_Bob_Smith.csv" in res.headers["content-disposition"]
    assert res.text == f"Student Name,Total Score,Session ID\nBob Smith,600,{sid}\n"


def test_receipt_not_found(client, played_session):
    sid = played_session["session"].id
    assert client.get(f"/receipt/{sid}/Nobody").status_code == 404


# --- GET /sessions/ ---

def test_sessions_lists_own_sessions_newest_first(client, db, professor, played_session):
    newer = models.GameSession(quiz_id=played_session["quiz"].id, room_code="NEW999")
    other_prof = make_user(db, "other@csumb.edu", is_professor=True)
    other_quiz = make_quiz(db, other_prof)
    db.add_all([newer, models.GameSession(quiz_id=other_quiz.id, room_code="NOTMINE")])
    db.commit()

    res = client.get("/sessions/", headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert [s["room_code"] for s in body] == ["NEW999", "ABC123"]
    assert body[1] == {
        "id": played_session["session"].id,
        "quiz_title": "Played Quiz",
        "room_code": "ABC123",
        "player_count": 2,
    }


def test_sessions_forbidden_for_student(client, student):
    assert client.get("/sessions/", headers=auth_header(student)).status_code == 403


# --- GET /analytics/{id} ---

def test_analytics_overview_questions_and_students(client, professor, played_session):
    res = client.get(f"/analytics/{played_session['session'].id}", headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert body["quiz_title"] == "Played Quiz"
    assert body["overview"] == {"total_students": 2, "average_score": 1200, "average_accuracy": 75}

    q1_stats, q2_stats = body["questions"]
    assert q1_stats["correct_count"] == 1
    assert q1_stats["incorrect_count"] == 1
    assert q1_stats["accuracy"] == 50
    assert q1_stats["spread"] == {"red": 0, "blue": 1, "yellow": 0, "green": 1}
    assert q2_stats["accuracy"] == 100
    assert q2_stats["spread"]["red"] == 2

    # Students are sorted by score, highest first
    assert [s["name"] for s in body["students"]] == ["Alice", "Bob Smith"]
    assert body["students"][0]["accuracy"] == 100
    assert body["students"][1]["accuracy"] == 50
    assert body["students"][1]["question_history"][0] == {
        "question_id": played_session["q1"].id,
        "selected_option": "green",
        "is_correct": False,
    }


def test_analytics_empty_session(client, db, professor):
    quiz = make_quiz(db, professor)
    session = models.GameSession(quiz_id=quiz.id, room_code="EMPTY1")
    db.add(session)
    db.commit()

    res = client.get(f"/analytics/{session.id}", headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert body["overview"] == {"total_students": 0, "average_score": 0, "average_accuracy": 0}
    assert body["questions"] == []
    assert body["students"] == []


def test_analytics_not_found(client, professor):
    assert client.get("/analytics/999", headers=auth_header(professor)).status_code == 404


def test_analytics_forbidden_for_other_professor(client, db, played_session):
    other = make_user(db, "other@csumb.edu", is_professor=True)
    res = client.get(f"/analytics/{played_session['session'].id}", headers=auth_header(other))
    assert res.status_code == 403


# --- GET /student/history ---

def test_student_history_details(client, student, played_session):
    res = client.get("/student/history", headers=auth_header(student))

    assert res.status_code == 200
    history = res.json()
    assert len(history) == 1
    entry = history[0]
    assert entry["quiz_title"] == "Played Quiz"
    assert entry["total_score"] == 1800
    assert entry["accuracy"] == 100

    d1, d2 = entry["details"]
    assert d1["question_text"] == "Q1"
    assert d1["selected_text"] == "4"      # option_blue
    assert d1["correct_text"] == "4"
    assert d1["explanation"] == "Basic math"
    assert d2["selected_text"] == "3"      # option_red
    assert d2["explanation"] == "No explanation provided by the instructor."


def test_student_history_newest_first(client, db, student, played_session):
    later = models.GameSession(quiz_id=played_session["quiz"].id, room_code="LATER1")
    db.add(later)
    db.commit()
    db.add(models.StudentResult(session_id=later.id, student_name="Alice", total_score=5,
                                correct_answers=0, user_id=student.id))
    db.commit()

    history = client.get("/student/history", headers=auth_header(student)).json()

    assert [h["total_score"] for h in history] == [5, 1800]
    assert history[0]["accuracy"] == 0  # no answers recorded -> no division by zero


def test_student_history_empty_for_new_user(client, db):
    newbie = make_user(db, "new@csumb.edu")
    res = client.get("/student/history", headers=auth_header(newbie))
    assert res.status_code == 200
    assert res.json() == []


def test_student_history_requires_auth(client):
    assert client.get("/student/history").status_code == 401
