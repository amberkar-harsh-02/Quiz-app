import pytest

import models
import main
from conftest import auth_header, make_quiz, make_session, make_user, question_data


@pytest.fixture
def played_session(db, professor, student):
    """A finished game: 2 questions, Alice (logged in) got both right, Bob got one right."""
    quiz = make_quiz(db, professor, "Played Quiz", questions=[
        question_data(text="Q1", correct="blue"),
        question_data(text="Q2", correct="red", explanation=None),
    ])
    q1, q2 = quiz.questions
    session = make_session(db, quiz)

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


# --- GET /sessions/ ---

def test_sessions_lists_own_sessions_newest_first(client, db, professor, played_session):
    make_session(db, played_session["quiz"], "NEW999")
    other_prof = make_user(db, "other@csumb.edu", is_professor=True)
    make_session(db, make_quiz(db, other_prof), "NOTMINE")

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
    session = make_session(db, make_quiz(db, professor), "EMPTY1")

    res = client.get(f"/analytics/{session.id}", headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert body["overview"] == {"total_students": 0, "average_score": 0, "average_accuracy": 0}
    assert body["questions"] == []
    assert body["students"] == []


def test_analytics_not_found(client, professor):
    assert client.get("/analytics/999", headers=auth_header(professor)).status_code == 404


# --- past results after the quiz is edited or deleted ---

def edit_first_question(client, professor, quiz):
    """Rewrites question 1: new text, new correct answer."""
    payload = {"title": "Renamed Quiz", "questions": [
        {**question_data(text="Q1 rewritten", correct="green")},
        {**question_data(text="Q2", correct="red")},
    ]}
    res = client.put(f"/quizzes/{quiz.id}", json=payload, headers=auth_header(professor))
    assert res.status_code == 200


def test_editing_a_played_quiz_keeps_past_results_as_played(client, professor, student, played_session):
    edit_first_question(client, professor, played_session["quiz"])

    analytics = client.get(f"/analytics/{played_session['session'].id}", headers=auth_header(professor)).json()
    assert analytics["quiz_title"] == "Played Quiz"
    assert [q["text"] for q in analytics["questions"]] == ["Q1", "Q2"]
    assert analytics["questions"][0]["accuracy"] == 50
    assert analytics["questions"][0]["spread"] == {"red": 0, "blue": 1, "yellow": 0, "green": 1}

    review = client.get("/student/history", headers=auth_header(student)).json()[0]
    assert review["quiz_title"] == "Played Quiz"
    assert review["details"][0]["question_text"] == "Q1"
    assert review["details"][0]["correct_option"] == "blue"
    assert review["details"][0]["is_correct"] == 1


def test_deleting_a_played_quiz_keeps_its_results(client, db, professor, student, played_session):
    assert client.delete(f"/quizzes/{played_session['quiz'].id}", headers=auth_header(professor)).status_code == 200

    sessions = client.get("/sessions/", headers=auth_header(professor)).json()
    assert [(s["quiz_title"], s["player_count"]) for s in sessions] == [("Played Quiz", 2)]
    analytics = client.get(f"/analytics/{played_session['session'].id}", headers=auth_header(professor))
    assert analytics.status_code == 200
    assert analytics.json()["overview"]["average_accuracy"] == 75
    review = client.get("/student/history", headers=auth_header(student)).json()
    assert review[0]["details"][0]["question_text"] == "Q1"


# --- games played before question copies existed ---

def test_backfill_gives_old_games_a_copy_of_their_questions(client, db, professor, student):
    quiz = make_quiz(db, professor, "Legacy Quiz", questions=[question_data(text="Old Q")])
    legacy = models.GameSession(quiz_id=quiz.id, room_code="OLD001")   # no title, owner or copy
    db.add(legacy)
    db.commit()

    main.backfill_session_snapshots()
    main.backfill_session_snapshots()   # safe to run on every startup

    db.expire_all()
    assert legacy.quiz_title == "Legacy Quiz"
    assert legacy.owner_id == professor.id
    assert [q.text for q in legacy.questions] == ["Old Q"]
    assert client.get(f"/analytics/{legacy.id}", headers=auth_header(professor)).status_code == 200


def test_backfill_handles_a_game_whose_quiz_is_gone(db):
    db.add(models.GameSession(quiz_id=999, room_code="ORPHAN"))
    db.commit()

    main.backfill_session_snapshots()

    session = db.query(models.GameSession).one()
    assert session.quiz_title == "Deleted quiz"
    assert session.questions == []


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
    assert entry["correct_answers"] == 2
    assert entry["total_questions"] == 2
    assert entry["session_id"] == played_session["session"].id
    assert entry["played_at"]

    d1, d2 = entry["details"]
    assert d1["question_text"] == "Q1"
    assert d1["selected_text"] == "4"      # option_blue
    assert d1["correct_text"] == "4"
    assert d1["explanation"] == "Basic math"
    assert d2["selected_text"] == "3"      # option_red
    assert d2["explanation"] == "No explanation provided by the instructor."


def test_student_history_newest_first(client, db, student, played_session):
    later = make_session(db, played_session["quiz"], "LATER1")
    db.add(models.StudentResult(session_id=later.id, student_name="Alice", total_score=5,
                                correct_answers=0, user_id=student.id))
    db.commit()

    history = client.get("/student/history", headers=auth_header(student)).json()

    assert [h["total_score"] for h in history] == [5, 1800]
    # Unanswered questions count as wrong, matching the professor's analytics
    assert history[0]["accuracy"] == 0
    assert history[0]["total_questions"] == 2


def test_student_history_empty_for_new_user(client, db):
    newbie = make_user(db, "new@csumb.edu")
    res = client.get("/student/history", headers=auth_header(newbie))
    assert res.status_code == 200
    assert res.json() == []


def test_student_history_requires_auth(client):
    assert client.get("/student/history").status_code == 401
