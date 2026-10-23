import csv
import io
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import auth_header, make_quiz, make_session, make_user, question_data
from test_websockets import end_game, recv_event, token_for


def play_and_end(client, quiz, professor, student=None):
    """Alice (signed in if `student`) answers Q1 correctly, guest Bob answers it wrong; returns game_over messages."""
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]
        alice_url = f"/ws/student/{code}?student_name=Alice" + (f"&token={token_for(student)}" if student else "")
        with client.websocket_connect(alice_url) as alice, \
             client.websocket_connect(f"/ws/student/{code}?student_name=Bob") as bob:
            alice.receive_json()
            bob.receive_json()
            recv_event(host, "player_joined")
            recv_event(host, "player_joined")
            host.send_json({"event": "start_game"})
            recv_event(alice, "show_question")
            recv_event(bob, "show_question")
            alice.send_json({"event": "submit_answer", "selected_option": "blue"})
            recv_event(host, "answer_received")
            bob.send_json({"event": "submit_answer", "selected_option": "red"})
            recv_event(host, "answer_received")
            host.send_json({"event": "show_leaderboard"})
            recv_event(host, "leaderboard")
            host.send_json({"event": "end_game"})
            return recv_event(alice, "game_over"), recv_event(bob, "game_over"), recv_event(host, "game_over")


# --- student review links ---

def test_review_links_only_when_professor_allows_them(client, db, professor):
    off = make_quiz(db, professor, "Off", questions=[question_data()])
    alice, bob, _ = play_and_end(client, off, professor)

    assert alice["review_url"] is None and bob["review_url"] is None
    assert db.query(models.StudentResult).filter(models.StudentResult.review_token.isnot(None)).count() == 0


def test_each_student_gets_their_own_review_pdf(client, db, professor, monkeypatch):
    quiz = make_quiz(db, professor, "Week 3 – Crypto", questions=[question_data(text="2 + 2?"), question_data(text="Q2")])
    quiz.student_review_pdf = True
    db.commit()
    alice, bob, _ = play_and_end(client, quiz, professor)
    assert alice["review_url"] != bob["review_url"]
    assert alice["review_url"].startswith("/review/") and alice["review_url"].endswith(".pdf")

    seen = {}
    real = main.review_pdf
    monkeypatch.setattr(main, "review_pdf", lambda **kw: seen.update(kw) or real(**kw))
    res = client.get(bob["review_url"])   # Bob is a guest: no sign-in needed

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert "attachment" in res.headers["content-disposition"]
    assert res.headers["cache-control"] == "private, no-store"
    assert seen["student_name"] == "Bob"
    assert seen["quiz_title"] == "Week 3 – Crypto"
    assert (seen["rank"], seen["total_players"], seen["correct"]) == (2, 2, 0)
    q1, q2 = seen["questions"]
    assert (q1["text"], q1["selected"], q1["selected_text"], q1["correct_option"], q1["correct_text"]) == ("2 + 2?", "red", "3", "blue", "4")
    assert q2["selected"] is None   # the game ended before question 2


def test_review_link_expires_after_a_week(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    session = make_session(db, quiz)
    db.add(models.StudentResult(session_id=session.id, student_name="Old", total_score=0, correct_answers=0, review_token="old-token"))
    session.created_at = datetime.utcnow() - timedelta(days=8)
    db.commit()

    res = client.get("/review/old-token.pdf")

    assert res.status_code == 410
    assert res.json()["detail"] == "This review link has expired."


def test_unknown_review_link_is_404(client):
    assert client.get("/review/nope.pdf").status_code == 404


def test_review_pdf_includes_question_image(client, db, professor):
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (300, 150), (31, 79, 143)).save(buf, "PNG")
    db.add(models.Image(id="c" * 32, owner_id=professor.id, content_type="image/png", data=buf.getvalue(), width=300, height=150))
    q = question_data()
    q.update(image_id="c" * 32)
    quiz = make_quiz(db, professor, questions=[q])
    session = make_session(db, quiz)
    db.add(models.StudentResult(session_id=session.id, student_name="Pic", total_score=0, correct_answers=0, review_token="pic-token"))
    db.commit()

    res = client.get("/review/pic-token.pdf")

    assert res.status_code == 200
    assert b"/Image" in res.content   # the picture is embedded


# --- professor downloads ---

@pytest.fixture
def finished_game(client, db, professor, student):
    quiz = make_quiz(db, professor, "Graded Quiz", questions=[question_data(text="2 + 2?")])
    play_and_end(client, quiz, professor, student)
    return db.query(models.GameSession).one()


def test_class_report_pdf(client, professor, finished_game):
    res = client.get(f"/analytics/{finished_game.id}/report.pdf", headers=auth_header(professor))

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert 'filename="graded-quiz-report.pdf"' in res.headers["content-disposition"]


def test_grades_csv(client, db, professor, finished_game):
    res = client.get(f"/analytics/{finished_game.id}/grades.csv", headers=auth_header(professor))

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows[0] == ["name", "email", "score", "correct", "total_questions", "accuracy_percent"]
    by_name = {r[0]: r for r in rows[1:]}
    assert by_name["Alice"][1:2] == ["student@csumb.edu"]
    assert by_name["Alice"][3:] == ["1", "1", "100"]
    assert by_name["Bob"][1] == ""          # guest: no email
    assert by_name["Bob"][2:] == ["0", "0", "1", "0"]


def test_grades_csv_neutralises_formula_nicknames(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    session = make_session(db, quiz)
    db.add(models.StudentResult(session_id=session.id, student_name='=HYPERLINK("http://x")', total_score=0, correct_answers=0))
    db.commit()

    rows = list(csv.reader(io.StringIO(client.get(f"/analytics/{session.id}/grades.csv", headers=auth_header(professor)).text)))

    assert rows[1][0] == '\'=HYPERLINK("http://x")'


def test_professor_downloads_a_students_review(client, db, professor, finished_game, monkeypatch):
    bob = db.query(models.StudentResult).filter_by(student_name="Bob").one()
    assert {s["name"]: s["result_id"] for s in client.get(f"/analytics/{finished_game.id}", headers=auth_header(professor)).json()["students"]}["Bob"] == bob.id
    finished_game.created_at = datetime.utcnow() - timedelta(days=30)   # the professor's copy never expires
    db.commit()

    seen = {}
    real = main.review_pdf
    monkeypatch.setattr(main, "review_pdf", lambda **kw: seen.update(kw) or real(**kw))
    res = client.get(f"/analytics/{finished_game.id}/students/{bob.id}/review.pdf", headers=auth_header(professor))

    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    assert 'filename="graded-quiz-bob-review.pdf"' in res.headers["content-disposition"]
    assert seen["student_name"] == "Bob"
    assert seen["questions"][0]["selected"] == "red"


def test_student_review_must_belong_to_the_session(client, db, professor, finished_game):
    other_session = make_session(db, make_quiz(db, professor, questions=[question_data()]), room_code="OTHER1")
    stranger = models.StudentResult(session_id=other_session.id, student_name="Eve", total_score=0, correct_answers=0)
    db.add(stranger)
    db.commit()

    res = client.get(f"/analytics/{finished_game.id}/students/{stranger.id}/review.pdf", headers=auth_header(professor))

    assert res.status_code == 404


def test_quiz_solutions_pdf(client, db, professor, monkeypatch):
    quiz = make_quiz(db, professor, "Week 3 – Crypto", questions=[question_data(text="2 + 2?"), question_data(text="Q2", correct="green", explanation="")])
    seen = {}
    real = main.solutions_pdf
    monkeypatch.setattr(main, "solutions_pdf", lambda **kw: seen.update(kw) or real(**kw))

    res = client.get(f"/quizzes/{quiz.id}/solutions.pdf", headers=auth_header(professor))

    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    assert 'filename="week-3---crypto-solutions.pdf"' in res.headers["content-disposition"]
    q1, q2 = seen["questions"]
    assert q1["options"] == {"red": "3", "blue": "4", "yellow": "5", "green": "22"}
    assert (q1["text"], q1["correct_option"], q1["explanation"]) == ("2 + 2?", "blue", "Basic math")
    assert (q2["correct_option"], q2["explanation"]) == ("green", "")


def test_session_solutions_use_the_questions_as_played(client, db, professor, monkeypatch):
    quiz = make_quiz(db, professor, questions=[question_data(text="Original wording")])
    session = make_session(db, quiz)
    quiz.questions[0].text = "Edited later"
    db.commit()
    seen = {}
    real = main.solutions_pdf
    monkeypatch.setattr(main, "solutions_pdf", lambda **kw: seen.update(kw) or real(**kw))

    res = client.get(f"/analytics/{session.id}/solutions.pdf", headers=auth_header(professor))

    assert res.status_code == 200
    assert seen["questions"][0]["text"] == "Original wording"


def test_quiz_solutions_are_owner_only(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    other = make_user(db, "other@csumb.edu", is_professor=True)
    assert client.get(f"/quizzes/{quiz.id}/solutions.pdf", headers=auth_header(other)).status_code == 403
    assert client.get(f"/quizzes/{quiz.id}/solutions.pdf").status_code == 401


@pytest.mark.parametrize("path", ["report.pdf", "grades.csv", "solutions.pdf", "students/{bob}/review.pdf"])
def test_downloads_are_owner_only(client, db, finished_game, path):
    path = path.format(bob=db.query(models.StudentResult).filter_by(student_name="Bob").one().id)
    other = make_user(db, "other@csumb.edu", is_professor=True)
    assert client.get(f"/analytics/{finished_game.id}/{path}", headers=auth_header(other)).status_code == 403
    assert client.get(f"/analytics/{finished_game.id}/{path}").status_code == 401


# --- final podium ---

def test_host_gets_final_top_three_with_shared_ranks(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    _, _, host_over = play_and_end(client, quiz, professor)

    podium = host_over["top_players"]
    assert [p["name"] for p in podium] == ["Alice", "Bob"]
    assert podium[0]["rank"] == 1 and podium[1]["rank"] == 2
    assert podium[0]["score"] > 0 and podium[1]["score"] == 0


def test_tied_players_share_a_place(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]
        with client.websocket_connect(f"/ws/student/{code}?student_name=A") as a, \
             client.websocket_connect(f"/ws/student/{code}?student_name=B") as b:
            a.receive_json(); b.receive_json()
            recv_event(host, "player_joined"); recv_event(host, "player_joined")
            host.send_json({"event": "start_game"})
            recv_event(a, "show_question"); recv_event(b, "show_question")
            host.send_json({"event": "show_leaderboard"})
            recv_event(host, "leaderboard")
            podium = end_game(host, a, b)["top_players"]
    assert [p["rank"] for p in podium] == [1, 1]


def test_no_podium_when_game_never_started(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        host.receive_json()
        assert end_game(host)["top_players"] == []
