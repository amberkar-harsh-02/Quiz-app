from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, File, UploadFile
import json
import time
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from database import engine, SessionLocal, add_missing_columns
import models, schemas
from game_manager import manager
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

# Only these accounts can host games; everyone else signs up as a student
PROFESSOR_EMAILS = {e.strip().lower() for e in os.getenv("PROFESSOR_EMAILS", "").split(",") if e.strip()}

# Answers that arrive this long after the timer ends (network lag) still count, for 0 speed bonus
ANSWER_GRACE_SECONDS = 1.0
MAX_NICKNAME_LENGTH = 20
COLORS = ("red", "blue", "yellow", "green")

if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set for the application. Please check your .env file.")

# Initialize database tables
models.Base.metadata.create_all(bind=engine)
add_missing_columns(engine)

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

def grant_professor_if_listed(user: models.User, db: Session):
    """Promotes an account whose email was added to PROFESSOR_EMAILS after it signed up."""
    if user.email in PROFESSOR_EMAILS and not user.is_professor:
        user.is_professor = True
        db.commit()


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
    if not current_user.is_professor:
        raise HTTPException(status_code=403, detail="Professors and TAs only.")
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
        is_professor=email in PROFESSOR_EMAILS
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

    grant_professor_if_listed(user, db)
    access_token = create_access_token(data={"sub": user.email, "is_professor": user.is_professor})
    return {"access_token": access_token, "token_type": "bearer"}

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
                is_professor=email in PROFESSOR_EMAILS
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            grant_professor_if_listed(user, db)

        access_token = create_access_token(data={"sub": user.email, "is_professor": user.is_professor})
        return {"access_token": access_token, "token_type": "bearer"}

    except ValueError as e:
        # Print the exact error to your terminal
        print(f"GOOGLE AUTH ERROR: {str(e)}")
        # Send the exact error back to the frontend
        raise HTTPException(status_code=401, detail=f"Google Error: {str(e)}")


# --- REST API ROUTES ---

def get_owned_quiz(quiz_id: int, db: Session, user: models.User) -> models.Quiz:
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    if quiz.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this quiz.")
    return quiz

def ensure_never_played(quiz: models.Quiz, db: Session, action: str):
    """Played quizzes back student grades, so changing or removing them would corrupt analytics."""
    if db.query(models.GameSession).filter(models.GameSession.quiz_id == quiz.id).first():
        raise HTTPException(
            status_code=409,
            detail=f"This quiz has been played, so it can't be {action}. Duplicate it to make changes."
        )

def save_quiz(db: Session, quiz: models.Quiz, payload: schemas.FullQuizPayload) -> models.Quiz:
    """Writes the title and replaces all questions in a single commit."""
    quiz.title = payload.title
    quiz.questions = [models.Question(**q.model_dump()) for q in payload.questions]
    db.add(quiz)
    db.commit()
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
    quiz = get_owned_quiz(quiz_id, db, current_user)
    ensure_never_played(quiz, db, "edited")
    return save_quiz(db, quiz, payload)

@app.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    quiz = get_owned_quiz(quiz_id, db, current_user)
    ensure_never_played(quiz, db, "deleted")

    # Questions are removed by the relationship's delete-orphan cascade
    db.delete(quiz)
    db.commit()

    return {"detail": "Quiz deleted successfully"}

@app.get("/quizzes/", response_model=list[schemas.Quiz])
def get_all_quizzes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    return db.query(models.Quiz).filter(models.Quiz.owner_id == current_user.id).all()

@app.get("/quizzes/{quiz_id}", response_model=schemas.Quiz)
def read_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # Owner-only: the response includes the correct answers
    return get_owned_quiz(quiz_id, db, current_user)

@app.post("/quizzes/{quiz_id}/questions/", response_model=schemas.Question)
def create_question_for_quiz(quiz_id: int, question: schemas.QuestionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    db_quiz = get_owned_quiz(quiz_id, db, current_user)
    ensure_never_played(db_quiz, db, "edited")

    db_question = models.Question(**question.model_dump(), quiz_id=quiz_id)
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question

@app.get("/sessions/")
def get_past_sessions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # 1. Get all quizzes owned by the professor
    quizzes = db.query(models.Quiz).filter(models.Quiz.owner_id == current_user.id).all()
    quiz_ids = [q.id for q in quizzes]

    # 2. Get all game sessions for those quizzes
    sessions = db.query(models.GameSession).filter(models.GameSession.quiz_id.in_(quiz_ids)).order_by(models.GameSession.id.desc()).all()

    result = []
    for s in sessions:
        quiz = db.query(models.Quiz).filter(models.Quiz.id == s.quiz_id).first()
        player_count = db.query(models.StudentResult).filter(models.StudentResult.session_id == s.id).count()
        result.append({
            "id": s.id,
            "quiz_title": quiz.title if quiz else "Unknown Quiz",
            "room_code": s.room_code,
            "player_count": player_count
        })
    return result


@app.get("/analytics/{session_id}")
def get_session_analytics(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    game_session = db.query(models.GameSession).filter(models.GameSession.id == session_id).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Game session not found.")

    quiz = db.query(models.Quiz).filter(models.Quiz.id == game_session.quiz_id).first()
    if quiz is None:
        raise HTTPException(status_code=404, detail="The quiz for this session no longer exists.")
    if quiz.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this session.")

    results = db.query(models.StudentResult).filter(models.StudentResult.session_id == session_id).all()
    questions = db.query(models.Question).filter(models.Question.quiz_id == quiz.id).all()

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
            models.StudentAnswer.question_id == q.id
        ).all()

        correct_count = sum(1 for a in answers if a.is_correct)
        incorrect_count = len(answers) - correct_count
        q_accuracy = (correct_count / len(answers) * 100) if answers else 0

        spread = {"red": 0, "blue": 0, "yellow": 0, "green": 0}
        for a in answers:
            if a.selected_option in spread:
                spread[a.selected_option] += 1

        question_stats.append({
            "question_id": q.id,
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
        "quiz_title": quiz.title,
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
        quiz = db.query(models.Quiz).filter(models.Quiz.id == session.quiz_id).first()
        total_questions = len(quiz.questions) if quiz else 0

        answers = db.query(models.StudentAnswer).filter(models.StudentAnswer.result_id == r.id).all()
        details = []

        for a in answers:
            q = db.query(models.Question).filter(models.Question.id == a.question_id).first()
            if q:
                details.append({
                    "question_text": q.text,
                    "selected_option": a.selected_option,
                    "selected_text": getattr(q, f"option_{a.selected_option}", a.selected_option),
                    "correct_option": q.correct_option,
                    "correct_text": getattr(q, f"option_{q.correct_option}", q.correct_option),
                    "is_correct": a.is_correct,
                    "explanation": q.explanation or "No explanation provided by the instructor."
                })

        history.append({
            "id": r.id,
            "session_id": r.session_id,
            "quiz_title": quiz.title if quiz else "Unknown Quiz",
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
    }
    if for_host:
        view["options"] = q["options"]
    return view

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
        if not user or not user.is_professor:
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
                "time_limit": q.time_limit_seconds,
                "explanation": q.explanation or ""
            } for q in quiz.questions
        ]
    finally:
        db.close()

    # 2. Token is valid and the professor owns this quiz, accept connection
    await websocket.accept()
    room_code = manager.create_room(quiz_id, websocket)
    await websocket.send_json({"event": "room_created", "room_code": room_code})

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
                        game_session = models.GameSession(quiz_id=quiz_id, room_code=room_code)
                        db.add(game_session)
                        db.flush()

                        for student in room["students"].values():
                            history = student.get("history", [])
                            result = models.StudentResult(
                                session_id=game_session.id,
                                student_name=student["name"],
                                total_score=student["score"],
                                correct_answers=sum(1 for ans in history if ans["is_correct"] == 1),
                                user_id=student.get("user_id")
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
                        })

                await websocket.send_json({
                    "event": "game_over",
                    "session_id": final_session_id
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
                time_limit = current_question["time_limit"]
                elapsed = time.monotonic() - room["question_started_at"]
                if elapsed > time_limit + ANSWER_GRACE_SECONDS:
                    continue
                time_remaining = min(max(time_limit - elapsed, 0), time_limit)

                is_correct = (selected_option == current_question["correct"])
                points = 500 + int(time_remaining / time_limit * 500) if is_correct else 0

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
