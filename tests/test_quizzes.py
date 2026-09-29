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


def test_upload_missing_title_or_questions(client, professor):
    # ValueError falls through to the generic handler, so this surfaces as a 500
    res = upload(client, professor, {"title": "x"})
    assert res.status_code == 500
    assert "title" in res.json()["detail"]


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

    res = client.get(f"/quizzes/{quiz.id}")

    assert res.status_code == 200
    assert res.json()["questions"][0]["text"] == "2 + 2?"


def test_read_quiz_not_found(client):
    assert client.get("/quizzes/999").status_code == 404


# --- POST /quizzes/{id}/questions/ ---

def test_add_question_to_quiz(client, db, professor):
    quiz = make_quiz(db, professor)
    q = question_data()
    del q["explanation"]

    res = client.post(f"/quizzes/{quiz.id}/questions/", json=q)

    assert res.status_code == 200
    assert res.json()["quiz_id"] == quiz.id
    assert db.query(models.Question).filter_by(quiz_id=quiz.id).count() == 1


def test_add_question_to_missing_quiz(client):
    q = question_data()
    del q["explanation"]
    assert client.post("/quizzes/999/questions/", json=q).status_code == 404


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
