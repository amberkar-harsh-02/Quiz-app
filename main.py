from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, File, UploadFile, Response
import csv
import io
import json
import secrets
import time
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from database import engine, SessionLocal, add_missing_columns
import models, schemas
from game_manager import manager
from images import MAX_UPLOAD_BYTES, clean_image
from pdfs import class_report_pdf, review_pdf, solutions_pdf
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from datetime import datetime, timedelta
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import ValidationError
import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

def email_list(name: str) -> set:
    return {e.strip().lower() for e in os.getenv(name, "").split(",") if e.strip()}

# Admins can host and also manage who else can (the Staff page). Everyone they add there is staff;
# everyone else is a student.
ADMIN_EMAILS = email_list("ADMIN_EMAILS")
# Older setting that granted host access directly. Its emails are copied onto the staff list at startup.
LEGACY_PROFESSOR_EMAILS = email_list("PROFESSOR_EMAILS")

# Answers that arrive this long after the timer ends (network lag) still count, for 0 speed bonus
ANSWER_GRACE_SECONDS = 1.0
# A correct answer is worth up to this much; the quiz's speed_weight decides how much of it is for speed
MAX_POINTS = 1000
# Questions without a timer still reward speed: full bonus within this many seconds...
UNTIMED_FULL_BONUS_SECONDS = 5
# ...fading to no bonus at this many seconds
UNTIMED_NO_BONUS_SECONDS = 60
MAX_NICKNAME_LENGTH = 20
# How long a student's review PDF link keeps working after the game
REVIEW_LINK_DAYS = 7
COLORS = ("red", "blue", "yellow", "green")

if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set for the application. Please check your .env file.")

# Initialize database tables
models.Base.metadata.create_all(bind=engine)
add_missing_columns(engine)


def seed_staff_emails():
    """Carries existing access over to the staff list, so nobody loses it when this feature arrives."""
    db = SessionLocal()
    try:
        listed = {row.email for row in db.query(models.StaffEmail).all()}
        professors = {u.email for u in db.query(models.User).filter(models.User.is_professor == True)}  # noqa: E712
        for email in sorted((professors | LEGACY_PROFESSOR_EMAILS) - listed - ADMIN_EMAILS):
            db.add(models.StaffEmail(email=email, added_by="(carried over)"))
        db.commit()
    finally:
        db.close()

seed_staff_emails()


def snapshot_questions(session: models.GameSession, questions):
    """Copies questions onto a finished game; analytics and reviews read only this copy."""
    session.questions = [
        models.SessionQuestion(
            question_id=q.id, position=i, text=q.text,
            option_red=q.option_red, option_blue=q.option_blue,
            option_yellow=q.option_yellow, option_green=q.option_green,
            correct_option=q.correct_option, explanation=q.explanation,
            image_id=q.image_id, image_alt=q.image_alt,
        )
        for i, q in enumerate(questions)
    ]

def backfill_session_snapshots():
    """Gives games played before snapshots existed their copy. Played quizzes used to be locked,
    so their current questions are exactly what was played."""
    db = SessionLocal()
    try:
        for session in db.query(models.GameSession).filter(models.GameSession.quiz_title.is_(None)):
            quiz = db.query(models.Quiz).filter(models.Quiz.id == session.quiz_id).first()
            if quiz is None:
                session.quiz_title = "Deleted quiz"
                continue
            session.quiz_title = quiz.title
            session.owner_id = quiz.owner_id
            if not session.questions:
                snapshot_questions(session, quiz.questions)
        db.commit()
    finally:
        db.close()

backfill_session_snapshots()

app = FastAPI(title="CST 315 Kahoot Clone")

# Auth uses a bearer header, not cookies, so credentials are not needed. In dev, allow the
# Vite server whether it was opened as localhost or 127.0.0.1.
frontend_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_origin_regex=None if frontend_origins else r"https?://[^/]+:5173",
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the analytics page read the file name of a downloaded report
    expose_headers=["Content-Disposition"],
)

# Dependency to safely open and close a database session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SECURITY & AUTHENTICATION ---

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def is_staff(db: Session, email: str) -> bool:
    return email in ADMIN_EMAILS or db.query(models.StaffEmail).filter(models.StaffEmail.email == email).first() is not None

def can_host(user: models.User) -> bool:
    # Admins always can, even before their stored flag catches up (e.g. ADMIN_EMAILS was just edited)
    return bool(user.is_professor) or user.email in ADMIN_EMAILS

def sync_role(user: models.User, db: Session):
    """Brings is_professor in line with the staff list, so additions and removals apply at sign-in."""
    should_host = is_staff(db, user.email)
    if user.is_professor != should_host:
        user.is_professor = should_host
        db.commit()

def login_response(user: models.User) -> dict:
    token = create_access_token(data={
        "sub": user.email,
        "is_professor": can_host(user),
        "is_admin": user.email in ADMIN_EMAILS,
    })
    return {"access_token": token, "token_type": "bearer"}


# --- AUTHORIZATION DEPENDENCIES ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_professor(current_user: models.User = Depends(get_current_user)):
    if not can_host(current_user):
        raise HTTPException(status_code=403, detail="Professors and TAs only.")
    return current_user

def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admins only.")
    return current_user


@app.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    email = user.email.lower()
    if not email.endswith("@csumb.edu"):
        raise HTTPException(status_code=400, detail="Only @csumb.edu email addresses are permitted.")

    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")

    hashed_pw = get_password_hash(user.password)
    new_user = models.User(
        email=email,
        hashed_password=hashed_pw,
        is_professor=is_staff(db, email)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username.lower()).first()

    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    sync_role(user, db)
    return login_response(user)

@app.post("/google-login")
def google_auth(request: schemas.GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            request.token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=60
        )
        email = idinfo['email'].lower()

        if not email.endswith("@csumb.edu"):
            raise HTTPException(status_code=403, detail="Only @csumb.edu accounts are permitted.")

        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = models.User(
                email=email,
                hashed_password="GOOGLE_SSO_USER",
                is_professor=is_staff(db, email)
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            sync_role(user, db)

        return login_response(user)

    except ValueError as e:
        # Print the exact error to your terminal
        print(f"GOOGLE AUTH ERROR: {str(e)}")
        # Send the exact error back to the frontend
        raise HTTPException(status_code=401, detail=f"Google Error: {str(e)}")


@app.get("/me")
def read_me(current_user: models.User = Depends(get_current_user)):
    # The login token's role flags can be out of date; the frontend asks here instead
    return {
        "email": current_user.email,
        "is_professor": can_host(current_user),
        "is_admin": current_user.email in ADMIN_EMAILS,
    }


# --- STAFF (admins only) ---

@app.get("/staff")
def list_staff(db: Session = Depends(get_db), _: models.User = Depends(get_current_admin)):
    rows = db.query(models.StaffEmail).order_by(models.StaffEmail.email).all()
    registered = {u.email for u in db.query(models.User).filter(models.User.email.in_([r.email for r in rows]))}
    return {
        "admins": sorted(ADMIN_EMAILS),
        "staff": [
            {
                "email": r.email,
                "signed_up": r.email in registered,
                "added_by": r.added_by,
                "added_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }

@app.post("/staff", status_code=201)
def add_staff(body: schemas.StaffAdd, db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    email = body.email.strip().lower()
    if not email.endswith("@csumb.edu"):
        raise HTTPException(status_code=400, detail="Only @csumb.edu email addresses can be added.")
    if email in ADMIN_EMAILS:
        raise HTTPException(status_code=400, detail="That email is already an admin.")
    if db.query(models.StaffEmail).filter(models.StaffEmail.email == email).first():
        raise HTTPException(status_code=409, detail="That email is already on the staff list.")

    db.add(models.StaffEmail(email=email, added_by=admin.email))
    # Takes effect right away for someone who already has an account
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        user.is_professor = True
    db.commit()
    return {"email": email, "signed_up": user is not None}

@app.delete("/staff/{email}")
def remove_staff(email: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_admin)):
    email = email.strip().lower()
    if email in ADMIN_EMAILS:
        raise HTTPException(status_code=400, detail="Admins are set in the server's ADMIN_EMAILS and can't be removed here.")
    row = db.query(models.StaffEmail).filter(models.StaffEmail.email == email).first()
    if not row:
        raise HTTPException(status_code=404, detail="That email isn't on the staff list.")

    db.delete(row)
    # Their next request is refused; quizzes they made are kept
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        user.is_professor = False
    db.commit()
    return {"detail": "Removed."}


# --- REST API ROUTES ---

def get_owned_quiz(quiz_id: int, db: Session, user: models.User) -> models.Quiz:
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    if quiz.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this quiz.")
    return quiz

def with_times_played(db: Session, quizzes):
    """Fills Quiz.times_played (shown in My Quizzes and the editor) with one query."""
    ids = [q.id for q in quizzes]
    counts = dict(
        db.query(models.GameSession.quiz_id, func.count(models.GameSession.id))
        .filter(models.GameSession.quiz_id.in_(ids))
        .group_by(models.GameSession.quiz_id)
    ) if ids else {}
    for q in quizzes:
        q.times_played = counts.get(q.id, 0)
    return quizzes

def image_url(image_id):
    return f"/images/{image_id}" if image_id else None

def delete_unused_images(db: Session, image_ids: set):
    """Deletes images nothing points at any more. Copies of a quiz share images, and past games
    keep theirs for student reviews, so check both first."""
    for image_id in image_ids:
        in_use = (
            db.query(models.Question).filter(models.Question.image_id == image_id).first()
            or db.query(models.SessionQuestion).filter(models.SessionQuestion.image_id == image_id).first()
        )
        if image_id and not in_use:
            db.query(models.Image).filter(models.Image.id == image_id).delete()
    db.commit()

def save_quiz(db: Session, quiz: models.Quiz, payload: schemas.FullQuizPayload) -> models.Quiz:
    """Writes the title and replaces all questions in a single commit."""
    wanted = {q.image_id for q in payload.questions if q.image_id}
    if wanted:
        owned = {i.id for i in db.query(models.Image.id).filter(models.Image.id.in_(wanted), models.Image.owner_id == quiz.owner_id)}
        if owned != wanted:
            raise HTTPException(status_code=400, detail="One of the question images wasn't found. Upload it again.")

    previous_images = {q.image_id for q in quiz.questions if q.image_id} if quiz.id else set()
    quiz.title = payload.title
    quiz.use_timer = payload.use_timer
    quiz.auto_advance_results = payload.auto_advance_results
    quiz.speed_weight = payload.speed_weight
    quiz.student_review_pdf = payload.student_review_pdf
    quiz.questions = [models.Question(**q.model_dump()) for q in payload.questions]
    db.add(quiz)
    db.commit()
    delete_unused_images(db, previous_images - wanted)
    db.refresh(quiz)
    return quiz

def describe_validation_error(e: ValidationError) -> str:
    err = e.errors()[0]
    location = " → ".join(str(part) for part in err["loc"])
    return f"{location}: {err['msg']}" if location else err["msg"]

@app.post("/quizzes/", response_model=schemas.Quiz)
def create_quiz(quiz: schemas.QuizCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # Automatically tie the quiz to the logged-in professor
    db_quiz = models.Quiz(title=quiz.title, owner_id=current_user.id)
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    return db_quiz

@app.post("/quizzes/upload/", response_model=schemas.Quiz)
async def upload_quiz_json(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_professor)
):
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only .json files are allowed.")

    try:
        payload = schemas.FullQuizPayload.model_validate(json.loads(await file.read()))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid quiz file. {describe_validation_error(e)}")

    return save_quiz(db, models.Quiz(owner_id=current_user.id), payload)

@app.post("/quizzes/builder", response_model=schemas.Quiz)
def create_quiz_from_builder(payload: schemas.FullQuizPayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    return save_quiz(db, models.Quiz(owner_id=current_user.id), payload)

@app.put("/quizzes/{quiz_id}", response_model=schemas.Quiz)
def update_quiz(quiz_id: int, payload: schemas.FullQuizPayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # Past games keep their own copy of the questions, so editing a played quiz is safe
    quiz = get_owned_quiz(quiz_id, db, current_user)
    return with_times_played(db, [save_quiz(db, quiz, payload)])[0]

@app.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    quiz = get_owned_quiz(quiz_id, db, current_user)

    # Past games and their results stay in Analytics; they keep their own copy of the questions.
    # Questions are removed by the relationship's delete-orphan cascade
    image_ids = {q.image_id for q in quiz.questions if q.image_id}
    db.delete(quiz)
    db.commit()
    delete_unused_images(db, image_ids)

    return {"detail": "Quiz deleted successfully"}

# --- QUESTION IMAGES ---

@app.post("/images", status_code=201)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Images can be at most 5 MB.")
    try:
        data, content_type, width, height = clean_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    image = models.Image(
        id=secrets.token_hex(16), owner_id=current_user.id,
        content_type=content_type, data=data, width=width, height=height,
    )
    db.add(image)
    db.commit()
    return {"id": image.id, "url": image_url(image.id), "width": width, "height": height}

@app.get("/images/{image_id}")
def get_image(image_id: str, db: Session = Depends(get_db)):
    # No sign-in: guests see question images during a game. IDs are random, so they can't be guessed.
    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            # An image never changes; editing a question uploads a new one with a new ID
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )

@app.get("/quizzes/", response_model=list[schemas.Quiz])
def get_all_quizzes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    return with_times_played(db, db.query(models.Quiz).filter(models.Quiz.owner_id == current_user.id).all())

@app.get("/quizzes/{quiz_id}", response_model=schemas.Quiz)
def read_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # Owner-only: the response includes the correct answers
    return with_times_played(db, [get_owned_quiz(quiz_id, db, current_user)])[0]

@app.post("/quizzes/{quiz_id}/duplicate", response_model=schemas.Quiz)
def duplicate_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    original = get_owned_quiz(quiz_id, db, current_user)
    copy = models.Quiz(
        title=f"Copy of {original.title}", owner_id=current_user.id,
        use_timer=original.use_timer, auto_advance_results=original.auto_advance_results,
        speed_weight=original.speed_weight, student_review_pdf=original.student_review_pdf,
        # Images are shared, not copied; they're only deleted once nothing uses them
        questions=[
            models.Question(**{f: getattr(q, f) for f in (
                "text", "option_red", "option_blue", "option_yellow", "option_green", "correct_option",
                "time_limit_seconds", "explanation", "image_id", "image_alt",
            )})
            for q in original.questions
        ],
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy

@app.post("/quizzes/{quiz_id}/questions/", response_model=schemas.Question)
def create_question_for_quiz(quiz_id: int, question: schemas.QuestionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    get_owned_quiz(quiz_id, db, current_user)

    db_question = models.Question(**question.model_dump(), quiz_id=quiz_id)
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question

@app.get("/sessions/")
def get_past_sessions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # Sessions carry their own owner and title, so games of edited or deleted quizzes still show
    sessions = db.query(models.GameSession).filter(models.GameSession.owner_id == current_user.id).order_by(models.GameSession.id.desc()).all()

    result = []
    for s in sessions:
        player_count = db.query(models.StudentResult).filter(models.StudentResult.session_id == s.id).count()
        result.append({
            "id": s.id,
            "quiz_title": s.quiz_title,
            "room_code": s.room_code,
            "player_count": player_count
        })
    return result


def owned_session(db: Session, session_id: int, user: models.User) -> models.GameSession:
    game_session = db.query(models.GameSession).filter(models.GameSession.id == session_id).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Game session not found.")
    if game_session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this session.")
    return game_session

def played_on(session: models.GameSession) -> str:
    return session.created_at.strftime("%B %d, %Y").replace(" 0", " ") if session.created_at else "unknown date"

def download_name(title: str, suffix: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in title).strip("-").lower() or "quiz"
    return f"{safe[:60]}-{suffix}"

@app.get("/analytics/{session_id}")
def get_session_analytics(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    return session_analytics(db, owned_session(db, session_id, current_user))

@app.get("/analytics/{session_id}/report.pdf")
def download_class_report(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    game_session = owned_session(db, session_id, current_user)
    data = class_report_pdf(
        analytics=session_analytics(db, game_session),
        questions=[
            {"text": q.text, "correct_option": q.correct_option, "correct_text": getattr(q, f"option_{q.correct_option}", "")}
            for q in game_session.questions
        ],
        room_code=game_session.room_code,
        played_on=played_on(game_session),
    )
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{download_name(game_session.quiz_title or "quiz", "report.pdf")}"',
    })

def csv_safe(value) -> str:
    # A nickname like "=HYPERLINK(...)" would run as a formula when the CSV is opened in a spreadsheet
    text_value = str(value)
    return "'" + text_value if text_value[:1] in ("=", "+", "-", "@") else text_value

@app.get("/analytics/{session_id}/grades.csv")
def download_grades(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    game_session = owned_session(db, session_id, current_user)
    total = len(game_session.questions)
    results = db.query(models.StudentResult).filter(models.StudentResult.session_id == session_id).order_by(models.StudentResult.total_score.desc()).all()
    emails = {u.id: u.email for u in db.query(models.User).filter(models.User.id.in_([r.user_id for r in results if r.user_id]))}

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["name", "email", "score", "correct", "total_questions", "accuracy_percent"])
    for r in results:
        writer.writerow([
            csv_safe(r.student_name), emails.get(r.user_id, ""), r.total_score, r.correct_answers, total,
            round(r.correct_answers / total * 100) if total else 0,
        ])
    return Response(content=out.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{download_name(game_session.quiz_title or "quiz", "grades.csv")}"',
    })

def solutions_response(db: Session, title: str, subtitle: str, rows) -> Response:
    """rows: Question or SessionQuestion objects, in order."""
    images = question_images(db, rows)
    questions = []
    for number, q in enumerate(rows, start=1):
        image = images.get(q.image_id)
        questions.append({
            "number": number,
            "text": q.text,
            "image": (image.data, image.width, image.height) if image else None,
            "options": {color: getattr(q, f"option_{color}") or "" for color in ("red", "blue", "yellow", "green")},
            "correct_option": q.correct_option,
            "explanation": q.explanation or "",
        })
    data = solutions_pdf(quiz_title=title, subtitle=subtitle, questions=questions)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{download_name(title, "solutions.pdf")}"',
    })

@app.get("/quizzes/{quiz_id}/solutions.pdf")
def download_quiz_solutions(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    quiz = get_owned_quiz(quiz_id, db, current_user)
    return solutions_response(db, quiz.title or "Quiz", "Answer key", quiz.questions)

@app.get("/analytics/{session_id}/solutions.pdf")
def download_session_solutions(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # The questions as they were played, even if the quiz was edited or deleted since
    game_session = owned_session(db, session_id, current_user)
    return solutions_response(db, game_session.quiz_title or "Quiz", f"Answer key, as played {played_on(game_session)}", game_session.questions)

@app.get("/review/{token}.pdf")
def download_review(token: str, db: Session = Depends(get_db)):
    # No sign-in: guests use this too. The random token is the key, and it stops working after a week.
    result = db.query(models.StudentResult).filter(models.StudentResult.review_token == token).first()
    if not result:
        raise HTTPException(status_code=404, detail="Review not found.")
    session = db.query(models.GameSession).filter(models.GameSession.id == result.session_id).first()
    if not session or not session.created_at or datetime.utcnow() - session.created_at > timedelta(days=REVIEW_LINK_DAYS):
        raise HTTPException(status_code=410, detail="This review link has expired.")
    return student_review_response(db, session, result, "review.pdf")

@app.get("/analytics/{session_id}/students/{result_id}/review.pdf")
def download_student_review(session_id: int, result_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # The professor's copy, e.g. to email to a guest; unlike the student's link it doesn't expire
    session = owned_session(db, session_id, current_user)
    result = db.query(models.StudentResult).filter(
        models.StudentResult.id == result_id, models.StudentResult.session_id == session.id
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Student result not found.")
    return student_review_response(db, session, result, download_name(result.student_name or "student", "review.pdf"))

def question_images(db: Session, rows) -> dict:
    return {i.id: i for i in db.query(models.Image).filter(models.Image.id.in_([q.image_id for q in rows if q.image_id]))}

def student_review_response(db: Session, session: models.GameSession, result: models.StudentResult, suffix: str) -> Response:
    answers = {a.question_id: a for a in db.query(models.StudentAnswer).filter(models.StudentAnswer.result_id == result.id)}
    scores = [r.total_score for r in db.query(models.StudentResult.total_score).filter(models.StudentResult.session_id == session.id)]
    images = question_images(db, session.questions)
    questions = []
    for number, q in enumerate(session.questions, start=1):
        answer = answers.get(q.question_id)
        image = images.get(q.image_id)
        questions.append({
            "number": number,
            "text": q.text,
            "image": (image.data, image.width, image.height) if image else None,
            "selected": answer.selected_option if answer else None,
            "selected_text": getattr(q, f"option_{answer.selected_option}", "") if answer else "",
            "correct_option": q.correct_option,
            "correct_text": getattr(q, f"option_{q.correct_option}", ""),
            "explanation": q.explanation or "",
        })

    data = review_pdf(
        quiz_title=session.quiz_title or "Quiz",
        played_on=played_on(session),
        student_name=result.student_name,
        score=result.total_score,
        rank=1 + sum(1 for s in scores if s > result.total_score),
        total_players=len(scores),
        correct=result.correct_answers,
        questions=questions,
    )
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{download_name(session.quiz_title or "quiz", suffix)}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })

def session_analytics(db: Session, game_session: models.GameSession) -> dict:
    session_id = game_session.id
    results = db.query(models.StudentResult).filter(models.StudentResult.session_id == session_id).all()
    # The questions as they were played, even if the quiz was edited or deleted since
    questions = game_session.questions

    total_students = len(results)

    # --- 1. Class Overview ---
    average_score = sum(r.total_score for r in results) / total_students if total_students > 0 else 0
    total_possible_correct = total_students * len(questions)
    total_actual_correct = sum(r.correct_answers for r in results)
    average_accuracy = (total_actual_correct / total_possible_correct * 100) if total_possible_correct > 0 else 0

    # --- 2. Question Breakdown ---
    question_stats = []
    for q in questions:
        answers = db.query(models.StudentAnswer).join(models.StudentResult).filter(
            models.StudentResult.session_id == session_id,
            models.StudentAnswer.question_id == q.question_id
        ).all()

        correct_count = sum(1 for a in answers if a.is_correct)
        incorrect_count = len(answers) - correct_count
        q_accuracy = (correct_count / len(answers) * 100) if answers else 0

        spread = {"red": 0, "blue": 0, "yellow": 0, "green": 0}
        for a in answers:
            if a.selected_option in spread:
                spread[a.selected_option] += 1

        question_stats.append({
            "question_id": q.question_id,
            "text": q.text,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "accuracy": round(q_accuracy),
            "spread": spread
        })

    # --- 3. Student Roster ---
    student_breakdowns = []
    for student in results:
        student_answers = db.query(models.StudentAnswer).filter(models.StudentAnswer.result_id == student.id).all()
        student_breakdowns.append({
            "result_id": student.id,
            "name": student.student_name,
            "final_score": student.total_score,
            "total_correct": student.correct_answers,
            "accuracy": round((student.correct_answers / len(questions) * 100) if questions else 0),
            "question_history": [
                {
                    "question_id": ans.question_id,
                    "selected_option": ans.selected_option,
                    "is_correct": bool(ans.is_correct)
                } for ans in student_answers
            ]
        })

    return {
        "session_id": game_session.id,
        "quiz_title": game_session.quiz_title,
        "overview": {
            "total_students": total_students,
            "average_score": round(average_score),
            "average_accuracy": round(average_accuracy)
        },
        "questions": question_stats,
        "students": sorted(student_breakdowns, key=lambda x: x["final_score"], reverse=True)
    }

@app.get("/student/history")
def get_student_history(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Find all past games played by this specific logged-in user
    results = db.query(models.StudentResult).filter(models.StudentResult.user_id == current_user.id).all()
    history = []

    for r in results:
        session = db.query(models.GameSession).filter(models.GameSession.id == r.session_id).first()
        if not session: continue
        # The questions as they were played, even if the quiz was edited or deleted since
        played = {q.question_id: q for q in session.questions}
        total_questions = len(played)

        answers = db.query(models.StudentAnswer).filter(models.StudentAnswer.result_id == r.id).all()
        details = []

        for a in answers:
            q = played.get(a.question_id)
            if q:
                details.append({
                    "question_text": q.text,
                    "selected_option": a.selected_option,
                    "selected_text": getattr(q, f"option_{a.selected_option}", a.selected_option),
                    "correct_option": q.correct_option,
                    "correct_text": getattr(q, f"option_{q.correct_option}", q.correct_option),
                    "is_correct": a.is_correct,
                    "explanation": q.explanation or "No explanation provided by the instructor.",
                    "image_url": image_url(q.image_id),
                    "image_alt": q.image_alt or "",
                })

        history.append({
            "id": r.id,
            "session_id": r.session_id,
            "quiz_title": session.quiz_title,
            "played_at": session.created_at.isoformat() if session.created_at else None,
            "total_score": r.total_score,
            "correct_answers": r.correct_answers,
            "total_questions": total_questions,
            # Same formula as the professor's analytics: unanswered questions count as wrong
            "accuracy": round(r.correct_answers / total_questions * 100) if total_questions else 0,
            "details": details
        })

    return list(reversed(history)) # Return newest first


# --- LIVE GAME HELPERS ---

def question_view(room: dict, for_host: bool = False) -> dict:
    """The current question (never includes the correct answer).

    Only the host gets the answer texts: students answer by letter while reading the
    choices off the projector, so their devices never receive them during a question.
    """
    index = room["current_question_index"]
    q = room["questions"][index]
    view = {
        "text": q["text"],
        "time_limit": q["time_limit"],
        "index": index,
        "total": len(room["questions"]),
        # Part of the question, so students get it too (unlike the answer texts)
        "image_url": q["image_url"],
        "image_alt": q["image_alt"],
    }
    if for_host:
        view["options"] = q["options"]
    return view

def speed_fraction(time_limit, elapsed: float):
    """How fast the answer was, from 0 (slow) to 1 (instant), or None if it came in too late to count."""
    if time_limit is None:
        # No deadline: full marks for speed early on, fading linearly to nothing
        fade = (UNTIMED_NO_BONUS_SECONDS - elapsed) / (UNTIMED_NO_BONUS_SECONDS - UNTIMED_FULL_BONUS_SECONDS)
        return min(max(fade, 0), 1)
    if elapsed > time_limit + ANSWER_GRACE_SECONDS:
        return None
    return min(max(time_limit - elapsed, 0), time_limit) / time_limit

def points_for_correct(speed: float, speed_weight: int) -> int:
    """speed_weight % of MAX_POINTS depends on speed; the rest is for being correct.

    At 50 this is the original 500 + up to 500 for speed. At 0 every correct answer gets MAX_POINTS.
    """
    weight = speed_weight / 100
    return round(MAX_POINTS * (1 - weight) + MAX_POINTS * weight * speed)

def answers_in(room: dict) -> int:
    """Answers to the current question from students who are still connected."""
    index = room["current_question_index"]
    return sum(
        1 for s in room["students"].values()
        if s["status"] == "online" and s.get("last_answered_index") == index
    )

def rank_of(room: dict, student: dict) -> int:
    # Tied scores share a rank
    return 1 + sum(1 for s in room["students"].values() if s["score"] > student["score"])

def answer_result(room: dict, student: dict) -> dict:
    """What one student sees after a question closes."""
    index = room["current_question_index"]
    q = room["questions"][index]
    answered = student.get("last_answered_index") == index
    selected = student.get("last_selected_option") if answered else None
    return {
        "event": "answer_result",
        "selected_option": selected,
        "correct": selected == q["correct"],
        "points_earned": student.get("last_points", 0) if answered else 0,
        "correct_option": q["correct"],
        "correct_text": q["options"][q["correct"]],
        "score": student["score"],
        "rank": rank_of(room, student),
        "total_players": len(room["students"]),
    }

async def notify_host(room: dict, message: dict):
    try:
        await room["host_ws"].send_json(message)
    except Exception:
        pass  # The host's own socket handler cleans up the room when it drops

async def send_to_student(student: dict, message: dict):
    try:
        await student["ws"].send_json(message)
    except Exception:
        student["status"] = "offline"

async def show_current_question(room_code: str, room: dict):
    room["current_state"] = "question_active"
    room["question_started_at"] = time.monotonic()
    await notify_host(room, {"event": "show_question", "question": question_view(room, for_host=True)})
    await manager.broadcast_to_students(room_code, {"event": "show_question", "question": question_view(room)})

async def show_results(room: dict):
    """Closes the current question: answer reveal for the host, personal result for each student."""
    room["current_state"] = "leaderboard"
    index = room["current_question_index"]
    q = room["questions"][index]

    spread = {color: 0 for color in COLORS}
    for s in room["students"].values():
        if s.get("last_answered_index") == index and s.get("last_selected_option") in spread:
            spread[s["last_selected_option"]] += 1

    ranked = sorted(room["students"].values(), key=lambda x: x["score"], reverse=True)
    await notify_host(room, {
        "event": "leaderboard",
        "top_players": [{"name": s["name"], "score": s["score"]} for s in ranked[:5]],
        "correct_option": q["correct"],
        "explanation": q["explanation"],
        "spread": spread,
        "is_last_question": index == len(room["questions"]) - 1,
        # Results count down to the next question only after a timed question in a quiz that allows it;
        # otherwise they wait for the professor
        "auto_advance": room.get("auto_advance_results", True) and q["time_limit"] is not None,
        "no_answer": sum(1 for s in room["students"].values() if s.get("last_answered_index") != index),
    })

    for s in room["students"].values():
        if s["status"] == "online":
            await send_to_student(s, answer_result(room, s))


# --- WEBSOCKETS ---

@app.websocket("/ws/host/{quiz_id}")
async def websocket_host(websocket: WebSocket, quiz_id: int, token: str = Query(...)):
    # 1. Verify the token and quiz ownership BEFORE accepting the WebSocket connection
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == payload.get("sub")).first()
        quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
        if not user or not can_host(user):
            await websocket.close(code=1008, reason="Professors only")
            return
        if not quiz or quiz.owner_id != user.id:
            await websocket.close(code=1008, reason="Quiz not found")
            return
        questions = [
            {
                "id": q.id,
                "text": q.text,
                "options": {
                    "red": q.option_red,
                    "blue": q.option_blue,
                    "yellow": q.option_yellow,
                    "green": q.option_green
                },
                "correct": q.correct_option,
                # None = no timer, either for this question or for the whole quiz
                "time_limit": q.time_limit_seconds if quiz.use_timer else None,
                "explanation": q.explanation or "",
                "image_url": image_url(q.image_id),
                "image_alt": q.image_alt or "",
            } for q in quiz.questions
        ]
        # Copied onto the finished game, so its results don't depend on the quiz afterwards
        snapshot_source = list(quiz.questions)
        quiz_title, owner_id = quiz.title, quiz.owner_id
        db.expunge_all()
        auto_advance_results = quiz.auto_advance_results
        speed_weight = quiz.speed_weight
        reviews_enabled = quiz.student_review_pdf
    finally:
        db.close()

    # 2. Token is valid and the professor owns this quiz, accept connection
    await websocket.accept()
    room_code = manager.create_room(quiz_id, websocket)
    manager.active_rooms[room_code]["auto_advance_results"] = auto_advance_results
    manager.active_rooms[room_code]["speed_weight"] = speed_weight
    await websocket.send_json({"event": "room_created", "room_code": room_code, "speed_weight": speed_weight})

    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")
            room = manager.active_rooms.get(room_code)
            if not room:
                continue

            if event == "start_game":
                if room["current_state"] == "lobby" and questions:
                    room["questions"] = questions
                    room["current_question_index"] = 0
                    await show_current_question(room_code, room)

            # Timer hitting 0 and clicking "Skip" both close the question; only the first one counts
            elif event in ["time_up", "show_leaderboard"]:
                if room["current_state"] == "question_active":
                    await show_results(room)

            elif event == "next_question":
                # Only from the leaderboard, so the auto-advance and a "Skip Delay" click can't skip a question
                if room["current_state"] == "leaderboard":
                    if room["current_question_index"] + 1 >= len(room["questions"]):
                        room["current_state"] = "finished"
                        await websocket.send_json({"event": "quiz_finished"})
                    else:
                        room["current_question_index"] += 1
                        await show_current_question(room_code, room)

            elif event == "end_game":
                final_session_id = None
                total_questions = len(room.get("questions", []))

                # A game that never started has no results worth keeping
                if total_questions:
                    db = SessionLocal()
                    try:
                        game_session = models.GameSession(
                            quiz_id=quiz_id, room_code=room_code, quiz_title=quiz_title, owner_id=owner_id,
                        )
                        snapshot_questions(game_session, snapshot_source)
                        db.add(game_session)
                        db.flush()

                        for student in room["students"].values():
                            history = student.get("history", [])
                            if reviews_enabled:
                                student["review_token"] = secrets.token_urlsafe(24)
                            result = models.StudentResult(
                                session_id=game_session.id,
                                student_name=student["name"],
                                total_score=student["score"],
                                correct_answers=sum(1 for ans in history if ans["is_correct"] == 1),
                                user_id=student.get("user_id"),
                                review_token=student.get("review_token"),
                            )
                            db.add(result)
                            db.flush()

                            for ans in history:
                                db.add(models.StudentAnswer(
                                    result_id=result.id,
                                    question_id=ans["question_id"],
                                    selected_option=ans["selected_option"],
                                    is_correct=ans["is_correct"]
                                ))

                        db.commit()
                        final_session_id = game_session.id
                    finally:
                        db.close()

                for student in room["students"].values():
                    if student["status"] == "online":
                        await send_to_student(student, {
                            "event": "game_over",
                            "session_id": final_session_id,
                            "score": student["score"],
                            "rank": rank_of(room, student),
                            "total_players": len(room["students"]),
                            "correct_answers": sum(1 for ans in student.get("history", []) if ans["is_correct"] == 1),
                            "total_questions": total_questions,
                            # Only when the professor allows reviews and the game was saved
                            "review_url": f"/review/{student['review_token']}.pdf" if final_session_id and student.get("review_token") else None,
                        })

                ranked = sorted(room["students"].values(), key=lambda s: s["score"], reverse=True)
                await websocket.send_json({
                    "event": "game_over",
                    "session_id": final_session_id,
                    # Final podium; tied scores share a place
                    "top_players": [
                        {"name": s["name"], "score": s["score"], "rank": rank_of(room, s)} for s in ranked[:3]
                    ] if total_questions else [],
                })

                del manager.active_rooms[room_code]

    except WebSocketDisconnect:
        # Host closed the tab mid-game: shut the room so students aren't left waiting
        room = manager.active_rooms.pop(room_code, None)
        if room:
            for student in room["students"].values():
                if student["status"] == "online":
                    await send_to_student(student, {"event": "host_left"})


@app.websocket("/ws/student/{room_code}")
async def websocket_student(
    websocket: WebSocket,
    room_code: str,
    student_name: str = Query(""),
    token: str = Query(None),
    player_id: str = Query(None),
):
    room_code = room_code.upper()
    await websocket.accept()

    async def reject(message: str):
        await websocket.send_json({"error": message})
        await websocket.close()

    room = manager.active_rooms.get(room_code)
    if not room:
        await reject("Invalid room code or room no longer exists.")
        return

    # 1. A student whose phone slept or lost Wi-Fi comes back with their player_id and keeps their score
    resumed = bool(player_id) and manager.reattach_student(room_code, player_id, websocket)

    if not resumed:
        student_name = student_name.strip()
        if not student_name or len(student_name) > MAX_NICKNAME_LENGTH:
            await reject(f"Nickname must be 1–{MAX_NICKNAME_LENGTH} characters.")
            return
        if manager.name_taken(room_code, student_name):
            await reject("That nickname is already taken in this room.")
            return

        # Check if they are a logged-in student or a guest
        user_id = None
        if token:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                db = SessionLocal()
                try:
                    user = db.query(models.User).filter(models.User.email == payload.get("sub")).first()
                    if user:
                        user_id = user.id
                finally:
                    db.close()
            except jwt.InvalidTokenError:
                pass # If the token is expired/invalid, let them play as a guest

        player_id = manager.add_student(room_code, student_name, websocket)
        room["students"][player_id]["user_id"] = user_id

    student = room["students"][player_id]
    await websocket.send_json({
        "event": "join_success",
        "player_id": player_id,
        "name": student["name"],
        "score": student["score"],
    })

    if resumed:
        await notify_host(room, {
            "event": "player_rejoined",
            "total_players": manager.online_count(room_code),
            "answers_submitted": answers_in(room) if room["current_state"] == "question_active" else 0,
        })
        # Put the student back where the game is right now
        if room["current_state"] == "question_active":
            index = room["current_question_index"]
            elapsed = time.monotonic() - room["question_started_at"]
            question = question_view(room)
            if question["time_limit"] is not None:
                question["time_remaining"] = max(0, question["time_limit"] - elapsed)
            if student.get("last_answered_index") == index:
                question["selected_option"] = student.get("last_selected_option")
            await websocket.send_json({"event": "show_question", "question": question})
        elif room["current_state"] in ("leaderboard", "finished"):
            await websocket.send_json(answer_result(room, student))
    else:
        await notify_host(room, {
            "event": "player_joined",
            "student_name": student["name"],
            "total_players": manager.online_count(room_code)
        })

    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")

            if event == "submit_answer":
                room = manager.active_rooms.get(room_code)
                if not room or room["current_state"] != "question_active":
                    continue

                current_q_index = room["current_question_index"]
                if student.get("last_answered_index") == current_q_index:
                    continue

                selected_option = data.get("selected_option")
                if selected_option not in COLORS:
                    continue

                # The server keeps the clock, so a client can't claim extra time for a bigger bonus
                current_question = room["questions"][current_q_index]
                elapsed = time.monotonic() - room["question_started_at"]
                speed = speed_fraction(current_question["time_limit"], elapsed)
                if speed is None:
                    continue

                is_correct = (selected_option == current_question["correct"])
                points = points_for_correct(speed, room.get("speed_weight", 50)) if is_correct else 0

                student["last_answered_index"] = current_q_index
                student["last_selected_option"] = selected_option
                student["last_points"] = points
                student["score"] += points
                student.setdefault("history", []).append({
                    "question_id": current_question["id"],
                    "selected_option": selected_option,
                    "is_correct": 1 if is_correct else 0
                })

                await notify_host(room, {
                    "event": "answer_received",
                    "answers_submitted": answers_in(room),
                    "total_players": manager.online_count(room_code)
                })

    except WebSocketDisconnect:
        room = manager.active_rooms.get(room_code)
        # Skip if a newer socket already took over this player (reconnect raced the old close)
        if room and student["ws"] is websocket:
            manager.mark_student_offline(room_code, player_id)
            # Tell the host so the "everyone answered" auto-skip doesn't wait for this student
            await notify_host(room, {
                "event": "player_left",
                "total_players": manager.online_count(room_code),
                "answers_submitted": answers_in(room) if room["current_state"] == "question_active" else 0,
            })
