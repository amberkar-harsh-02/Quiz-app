from io import BytesIO

import pytest
from PIL import Image

import models
from conftest import auth_header, make_quiz, make_user, question_data


def picture(fmt="PNG", size=(40, 30), exif=None):
    out = BytesIO()
    img = Image.new("RGB", size, (31, 79, 143))
    if exif is not None:
        img.save(out, fmt, exif=exif)
    else:
        img.save(out, fmt)
    return out.getvalue()


def upload(client, user, data, filename="diagram.png", content_type="image/png"):
    return client.post("/images", files={"file": (filename, data, content_type)}, headers=auth_header(user))


# --- uploading ---

def test_professor_uploads_png_and_it_stays_png(client, db, professor):
    res = upload(client, professor, picture("PNG"))

    assert res.status_code == 201
    body = res.json()
    assert body["url"] == f"/images/{body['id']}"
    assert (body["width"], body["height"]) == (40, 30)
    stored = db.get(models.Image, body["id"])
    assert stored.content_type == "image/png"
    assert stored.owner_id == professor.id
    assert len(body["id"]) == 32


def test_large_jpeg_is_shrunk_and_loses_its_metadata(client, db, professor):
    exif = Image.Exif()
    exif[0x8825] = {2: (36.0, 39.0, 15.0)}   # GPS info, like a phone photo
    exif[0x010F] = "PhoneMaker"              # camera make
    res = upload(client, professor, picture("JPEG", size=(4000, 3000), exif=exif), "photo.jpg", "image/jpeg")

    assert res.status_code == 201
    assert (res.json()["width"], res.json()["height"]) == (1600, 1200)
    stored = Image.open(BytesIO(db.get(models.Image, res.json()["id"]).data))
    assert stored.format == "JPEG"
    assert len(stored.getexif()) == 0


def test_file_that_is_not_really_an_image_is_rejected(client, professor):
    res = upload(client, professor, b"<script>alert(1)</script>", "evil.png", "image/png")
    assert res.status_code == 400
    assert res.json()["detail"] == "Only JPG and PNG images are allowed."


def test_other_image_formats_are_rejected(client, professor):
    res = upload(client, professor, picture("GIF"), "anim.gif", "image/gif")
    assert res.status_code == 400


def test_upload_over_5_mb_is_rejected(client, professor):
    res = upload(client, professor, b"\x89PNG" + b"0" * (5 * 1024 * 1024))
    assert res.status_code == 413


def test_students_cannot_upload(client, student):
    assert upload(client, student, picture()).status_code == 403


# --- serving ---

def test_image_is_served_with_safe_headers(client, professor):
    image_id = upload(client, professor, picture()).json()["id"]

    res = client.get(f"/images/{image_id}")   # no sign-in needed

    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in res.headers["cache-control"]
    assert Image.open(BytesIO(res.content)).size == (40, 30)


def test_unknown_image_is_404(client):
    assert client.get("/images/" + "0" * 32).status_code == 404


# --- using images in quizzes ---

def quiz_payload(image_id, title="With picture"):
    q = question_data()
    q.update(image_id=image_id, image_alt="A chart")
    return {"title": title, "questions": [q]}


def test_quiz_saves_image_and_alt_text(client, professor):
    image_id = upload(client, professor, picture()).json()["id"]
    res = client.post("/quizzes/builder", json=quiz_payload(image_id), headers=auth_header(professor))

    assert res.status_code == 200
    question = res.json()["questions"][0]
    assert question["image_id"] == image_id
    assert question["image_alt"] == "A chart"


def test_quiz_cannot_use_another_professors_image(client, db, professor):
    other = make_user(db, "other@csumb.edu", is_professor=True)
    image_id = upload(client, other, picture()).json()["id"]

    res = client.post("/quizzes/builder", json=quiz_payload(image_id), headers=auth_header(professor))

    assert res.status_code == 400


def test_deleting_a_quiz_removes_images_only_it_used(client, db, professor):
    shared = upload(client, professor, picture()).json()["id"]
    own = upload(client, professor, picture()).json()["id"]
    keep = client.post("/quizzes/builder", json=quiz_payload(shared, "Copy"), headers=auth_header(professor)).json()
    payload = quiz_payload(shared)
    payload["questions"].append({**question_data(text="Q2"), "image_id": own})
    doomed = client.post("/quizzes/builder", json=payload, headers=auth_header(professor)).json()

    assert client.delete(f"/quizzes/{doomed['id']}", headers=auth_header(professor)).status_code == 200

    db.expire_all()
    assert db.get(models.Image, own) is None
    assert db.get(models.Image, shared) is not None
    assert keep["questions"][0]["image_id"] == shared


def test_removing_image_from_question_deletes_it(client, db, professor):
    image_id = upload(client, professor, picture()).json()["id"]
    quiz = client.post("/quizzes/builder", json=quiz_payload(image_id), headers=auth_header(professor)).json()

    res = client.put(f"/quizzes/{quiz['id']}", json=quiz_payload(None), headers=auth_header(professor))

    assert res.status_code == 200
    db.expire_all()
    assert db.get(models.Image, image_id) is None
