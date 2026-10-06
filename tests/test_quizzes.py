import json

import models
from conftest import auth_header, make_quiz, make_user, question_data


def builder_question(**overrides):
    q = question_data()
    q.update(overrides)
    return q


# --- POST /quizzes/ ---

def test_create_quiz_owned_by_current_professor(client, professor):
    res = client.post("/quizzes/", json={"title": "Midterm"}, headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Midterm"
    assert body["owner_id"] == professor.id
    assert body["questions"] == []


def test_create_quiz_forbidden_for_student(client, student):
    res = client.post("/quizzes/", json={"title": "Midterm"}, headers=auth_header(student))
    assert res.status_code == 403


# --- POST /quizzes/builder ---

def test_builder_creates_quiz_with_questions(client, db, professor):
    payload = {
        "title": "Built Quiz",
        "questions": [
            builder_question(text="Q1"),
            builder_question(text="Q2", correct_option="red", time_limit_seconds=10),
        ],
    }
    res = client.post("/quizzes/builder", json=payload, headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert [q["text"] for q in body["questions"]] == ["Q1", "Q2"]
    assert body["questions"][1]["correct_option"] == "red"
    assert body["questions"][1]["time_limit_seconds"] == 10
    assert db.query(models.Question).count() == 2


def test_builder_applies_defaults(client, db, professor):
    q = builder_question()
    del q["time_limit_seconds"]
    del q["explanation"]
    res = client.post("/quizzes/builder", json={"title": "T", "questions": [q]}, headers=auth_header(professor))

    assert res.status_code == 200
    stored = db.query(models.Question).one()
    assert stored.time_limit_seconds == 15
    assert stored.explanation == ""


def test_builder_saves_timer_settings(client, db, professor):
    payload = {
        "title": "Discussion",
        "use_timer": False,
        "questions": [builder_question(text="Untimed", time_limit_seconds=None), builder_question(text="Timed")],
    }
    res = client.post("/quizzes/builder", json=payload, headers=auth_header(professor))

    assert res.status_code == 200
    body = res.json()
    assert body["use_timer"] is False
    assert [q["time_limit_seconds"] for q in body["questions"]] == [None, 20]


def test_builder_defaults_to_timer_on(client, professor):
    res = client.post("/quizzes/builder", json={"title": "T", "questions": [builder_question()]}, headers=auth_header(professor))
    assert res.json()["use_timer"] is True
    assert res.json()["auto_advance_results"] is True


def test_builder_saves_results_pacing(client, professor):
    payload = {"title": "Paced", "auto_advance_results": False, "questions": [builder_question()]}
    res = client.post("/quizzes/builder", json=payload, headers=auth_header(professor))
    assert res.status_code == 200
    assert res.json()["auto_advance_results"] is False


def test_upload_accepts_untimed_questions(client, professor):
    q = builder_question()
    q["time_limit_seconds"] = None
    res = upload(client, professor, {"title": "x", "use_timer": True, "questions": [q]})
    assert res.status_code == 200
    assert res.json()["questions"][0]["time_limit_seconds"] is None


def test_builder_rejects_incomplete_question(client, professor):
    q = builder_question()
    del q["option_green"]
    res = client.post("/quizzes/builder", json={"title": "T", "questions": [q]}, headers=auth_header(professor))
    assert res.status_code == 422


# --- POST /quizzes/upload/ ---

def upload(client, user, content, filename="quiz.json"):
    if not isinstance(content, (bytes, str)):
        content = json.dumps(content)
    return client.post(
        "/quizzes/upload/",
        files={"file": (filename, content, "application/json")},
        headers=auth_header(user),
    )


def test_upload_json_creates_quiz(client, db, professor):
    q = builder_question()
    del q["time_limit_seconds"]
    res = upload(client, professor, {"title": "Uploaded", "questions": [q, builder_question(text="Q2")]})

    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Uploaded"
    assert len(body["questions"]) == 2
    assert body["questions"][0]["time_limit_seconds"] == 15  # default when omitted


def test_upload_rejects_non_json_extension(client, professor):
    res = upload(client, professor, {"title": "x", "questions": []}, filename="quiz.txt")
    assert res.status_code == 400
    assert res.json()["detail"] == "Only .json files are allowed."


def test_upload_rejects_malformed_json(client, professor):
    res = upload(client, professor, "{not json")
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid JSON format."


def test_upload_rejects_question_missing_field(client, professor):
    q = builder_question()
    del q["correct_option"]
    res = upload(client, professor, {"title": "x", "questions": [q]})
    assert res.status_code == 400
    assert "correct_option" in res.json()["detail"]


def test_upload_missing_questions(client, professor):
    res = upload(client, professor, {"title": "x"})
    assert res.status_code == 400
    assert "questions" in res.json()["detail"]


def test_upload_rejects_invalid_color_and_time_limit(client, db, professor):
    res = upload(client, professor, {"title": "x", "questions": [builder_question(correct_option="purple")]})
    assert res.status_code == 400
    assert "correct_option" in res.json()["detail"]

    res = upload(client, professor, {"title": "x", "questions": [builder_question(time_limit_seconds=0)]})
    assert res.status_code == 400
    assert "time_limit_seconds" in res.json()["detail"]

    # Nothing half-saved from the rejected files
    assert db.query(models.Quiz).count() == 0


def test_upload_forbidden_for_student(client, student):
    res = upload(client, student, {"title": "x", "questions": []})
    assert res.status_code == 403


# --- GET /quizzes/ and /quizzes/{id} ---

def test_list_quizzes_only_returns_own(client, db, professor):
    other = make_user(db, "other@csumb.edu", is_professor=True)
    make_quiz(db, professor, "Mine 1")
    make_quiz(db, professor, "Mine 2")
    make_quiz(db, other, "Theirs")

    res = client.get("/quizzes/", headers=auth_header(professor))

    assert res.status_code == 200
    assert sorted(q["title"] for q in res.json()) == ["Mine 1", "Mine 2"]


def test_read_quiz_includes_questions(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])

    res = client.get(f"/quizzes/{quiz.id}", headers=auth_header(professor))

    assert res.status_code == 200
    assert res.json()["questions"][0]["text"] == "2 + 2?"
    assert res.json()["questions"][0]["explanation"] == "Basic math"


def test_read_quiz_not_found(client, professor):
    assert client.get("/quizzes/999", headers=auth_header(professor)).status_code == 404


def test_read_quiz_hides_answers_from_others(client, db, professor, student):
    # The response contains correct answers, so students must not be able to fetch it mid-game
    quiz = make_quiz(db, professor, questions=[question_data()])
    assert client.get(f"/quizzes/{quiz.id}").status_code == 401
    assert client.get(f"/quizzes/{quiz.id}", headers=auth_header(student)).status_code == 403
    other = make_user(db, "other@csumb.edu", is_professor=True)
    assert client.get(f"/quizzes/{quiz.id}", headers=auth_header(other)).status_code == 403


# --- POST /quizzes/{id}/questions/ ---

def test_add_question_to_quiz(client, db, professor):
    quiz = make_quiz(db, professor)
    q = question_data()
    del q["explanation"]

    res = client.post(f"/quizzes/{quiz.id}/questions/", json=q, headers=auth_header(professor))

    assert res.status_code == 200
    assert res.json()["quiz_id"] == quiz.id
    assert db.query(models.Question).filter_by(quiz_id=quiz.id).count() == 1


def test_add_question_to_missing_quiz(client, professor):
    q = question_data()
    del q["explanation"]
    assert client.post("/quizzes/999/questions/", json=q, headers=auth_header(professor)).status_code == 404


def test_add_question_requires_owner(client, db, professor):
    quiz = make_quiz(db, professor)
    assert client.post(f"/quizzes/{quiz.id}/questions/", json=question_data()).status_code == 401


# --- PUT /quizzes/{id} ---

def test_update_quiz_replaces_title_and_questions(client, db, professor):
    quiz = make_quiz(db, professor, "Old", questions=[question_data(text="Old Q1"), question_data(text="Old Q2")])
    payload = {"title": "New", "questions": [builder_question(text="New Q1", correct_option="green")]}

    res = client.put(f"/quizzes/{quiz.id}", json=payload, headers=auth_header(professor))

    assert res.status_code == 200
    assert res.json()["title"] == "New"
    assert [q["text"] for q in res.json()["questions"]] == ["New Q1"]
    db.expire_all()
    assert db.query(models.Question).count() == 1


def test_update_quiz_owned_by_someone_else(client, db, professor):
    other = make_user(db, "other@csumb.edu", is_professor=True)
    quiz = make_quiz(db, other)
    payload = {"title": "Hijack", "questions": [builder_question()]}
    assert client.put(f"/quizzes/{quiz.id}", json=payload, headers=auth_header(professor)).status_code == 403


def test_update_quiz_blocked_once_played(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    db.add(models.GameSession(quiz_id=quiz.id, room_code="PLAYED"))
    db.commit()
    payload = {"title": "New", "questions": [builder_question()]}

    res = client.put(f"/quizzes/{quiz.id}", json=payload, headers=auth_header(professor))

    assert res.status_code == 409
    assert "Duplicate" in res.json()["detail"]


# --- DELETE /quizzes/{id} ---

def test_delete_quiz_removes_quiz_and_questions(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data(), question_data(text="Q2")])

    res = client.delete(f"/quizzes/{quiz.id}", headers=auth_header(professor))

    assert res.status_code == 200
    db.expire_all()
    assert db.query(models.Quiz).count() == 0
    assert db.query(models.Question).count() == 0


def test_delete_quiz_not_found(client, professor):
    assert client.delete("/quizzes/999", headers=auth_header(professor)).status_code == 404


def test_delete_quiz_owned_by_someone_else(client, db, professor):
    other = make_user(db, "other@csumb.edu", is_professor=True)
    quiz = make_quiz(db, other)

    res = client.delete(f"/quizzes/{quiz.id}", headers=auth_header(professor))

    assert res.status_code == 403
    assert db.query(models.Quiz).count() == 1


def test_delete_quiz_blocked_once_played(client, db, professor):
    # Deleting would orphan the session's grades and break analytics
    quiz = make_quiz(db, professor, questions=[question_data()])
    db.add(models.GameSession(quiz_id=quiz.id, room_code="PLAYED"))
    db.commit()

    res = client.delete(f"/quizzes/{quiz.id}", headers=auth_header(professor))

    assert res.status_code == 409
    assert db.query(models.Quiz).count() == 1
