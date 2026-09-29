from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Response, Query, File, UploadFile
import json
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from database import engine, SessionLocal
import models, schemas
from game_manager import manager
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from datetime import datetime, timedelta
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set for the application. Please check your .env file.")

# Initialize database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="CST 315 Kahoot Clone")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows your local HTML files to request data
    allow_credentials=True,
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
    if not user.email.lower().endswith("@csumb.edu"):
        raise HTTPException(status_code=400, detail="Only @csumb.edu email addresses are permitted.")
    
    existing_user = db.query(models.User).filter(models.User.email == user.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    hashed_pw = get_password_hash(user.password)
    new_user = models.User(
        email=user.email.lower(),
        hashed_password=hashed_pw,
        is_professor=user.is_professor
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
                is_professor=False 
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
        access_token = create_access_token(data={"sub": user.email, "is_professor": user.is_professor})
        return {"access_token": access_token, "token_type": "bearer"}
        
    except ValueError as e:
        # Print the exact error to your terminal
        print(f"GOOGLE AUTH ERROR: {str(e)}") 
        # Send the exact error back to the frontend
        raise HTTPException(status_code=401, detail=f"Google Error: {str(e)}")


# --- REST API ROUTES ---

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
        contents = await file.read()
        data = json.loads(contents)
        
        if "title" not in data or "questions" not in data:
            raise ValueError("JSON must contain 'title' and 'questions' arrays.")
            
        # 1. Create the Quiz
        db_quiz = models.Quiz(title=data["title"], owner_id=current_user.id)
        db.add(db_quiz)
        db.commit()
        db.refresh(db_quiz)
        
        # 2. Iterate and create all Questions
        for q in data["questions"]:
            db_question = models.Question(
                quiz_id=db_quiz.id,
                text=q["text"],
                option_red=q["option_red"],
                option_blue=q["option_blue"],
                option_yellow=q["option_yellow"],
                option_green=q["option_green"],
                correct_option=q["correct_option"],
                time_limit_seconds=q.get("time_limit_seconds", 15),
                explanation=q.get("explanation", "")
            )
            db.add(db_question)
        
        db.commit()
        db.refresh(db_quiz)
        return db_quiz
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field in question: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

# --- NEW BUILDER & DELETE ROUTES ---

# Pydantic models for the visual builder payload
class QuestionBuilderItem(BaseModel):
    text: str
    option_red: str
    option_blue: str
    option_yellow: str
    option_green: str
    correct_option: str
    time_limit_seconds: int = 15
    explanation: str = ""

class FullQuizPayload(BaseModel):
    title: str
    questions: list[QuestionBuilderItem]

@app.post("/quizzes/builder", response_model=schemas.Quiz)
def create_quiz_from_builder(payload: FullQuizPayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    # 1. Create the Quiz
    db_quiz = models.Quiz(title=payload.title, owner_id=current_user.id)
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    
    # 2. Add all questions
    for q in payload.questions:
        db_question = models.Question(
            quiz_id=db_quiz.id,
            text=q.text,
            option_red=q.option_red,
            option_blue=q.option_blue,
            option_yellow=q.option_yellow,
            option_green=q.option_green,
            correct_option=q.correct_option,
            time_limit_seconds=q.time_limit_seconds,
            explanation=q.explanation
        )
        db.add(db_question)
    
    db.commit()
    db.refresh(db_quiz)
    return db_quiz

@app.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    if quiz.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this quiz.")
        
    # Delete associated questions first, then the quiz
    db.query(models.Question).filter(models.Question.quiz_id == quiz_id).delete()
    db.delete(quiz)
    db.commit()
    
    return {"detail": "Quiz deleted successfully"}

@app.get("/quizzes/", response_model=list[schemas.Quiz])
def get_all_quizzes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_professor)):
    return db.query(models.Quiz).filter(models.Quiz.owner_id == current_user.id).all()

@app.get("/quizzes/{quiz_id}", response_model=schemas.Quiz)
def read_quiz(quiz_id: int, db: Session = Depends(get_db)):
    db_quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if db_quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return db_quiz

@app.post("/quizzes/{quiz_id}/questions/", response_model=schemas.Question)
def create_question_for_quiz(quiz_id: int, question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    db_quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if db_quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    db_question = models.Question(**question.model_dump(), quiz_id=quiz_id)
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question

@app.get("/receipt/{session_id}/{student_name}")
def download_receipt(session_id: int, student_name: str, db: Session = Depends(get_db)):
    result = db.query(models.StudentResult).filter(
        models.StudentResult.session_id == session_id,
        models.StudentResult.student_name == student_name
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Student result not found.")

    csv_content = f"Student Name,Total Score,Session ID\n{result.student_name},{result.total_score},{result.session_id}\n"
    filename = f"cst315_receipt_{student_name.replace(' ', '_')}.csv"
    return Response(
        content=csv_content, 
        media_type="text/csv", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

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
            "quiz_title": quiz.title if quiz else "Unknown Quiz",
            "total_score": r.total_score,
            "accuracy": round((r.correct_answers / len(details) * 100)) if details else 0,
            "details": details
        })
        
    return list(reversed(history)) # Return newest first


# --- WEBSOCKETS ---

@app.websocket("/ws/host/{quiz_id}")
async def websocket_host(websocket: WebSocket, quiz_id: int, token: str = Query(...)):
    # 1. Verify the token BEFORE accepting the WebSocket connection
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("is_professor"):
            await websocket.close(code=1008, reason="Professors only")
            return
    except jwt.InvalidTokenError:
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    # 2. Token is valid and user is a professor, accept connection
    await websocket.accept()
    room_code = manager.create_room(quiz_id, websocket)
    await websocket.send_json({"event": "room_created", "room_code": room_code})
    
    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")
            room = manager.active_rooms.get(room_code)
            
            if event == "start_game":
                db = SessionLocal()
                quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
                
                if quiz and quiz.questions:
                    room["questions"] = [
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
                            "time_limit": q.time_limit_seconds
                        } for q in quiz.questions
                    ]
                    room["current_state"] = "question_active"
                    room["current_question_index"] = 0
                    
                    first_question = room["questions"][0]
                    
                    question_payload = {
                        "event": "show_question",
                        "question": {
                            "text": first_question["text"],
                            "options": first_question["options"],
                            "time_limit": first_question["time_limit"]
                        }
                    }
                    
                    await websocket.send_json(question_payload)
                    await manager.broadcast_to_students(room_code, question_payload)
                db.close()
                
            # FIX: Both Timer hitting 0 AND clicking "Skip" now trigger the exact same auto-transition
            elif event in ["time_up", "show_leaderboard"]:
                if room:
                    room["current_state"] = "leaderboard"
                    ranked_students = sorted(
                        room["students"].values(), 
                        key=lambda x: x["score"], 
                        reverse=True
                    )
                    
                    top_5 = [
                        {"name": s["name"], "score": s["score"]} 
                        for s in ranked_students[:5]
                    ]
                    
                    await websocket.send_json({
                        "event": "leaderboard",
                        "top_players": top_5
                    })

                    # FIX: Broadcast a map of player_id -> score to all students to avoid websocket crashes
                    scores_map = {p_id: s["score"] for p_id, s in room["students"].items()}
                    await manager.broadcast_to_students(room_code, {
                        "event": "leaderboard",
                        "scores": scores_map
                    })

            elif event == "next_question":
                if room:
                    room["current_question_index"] += 1
                    current_q_index = room["current_question_index"]
                    
                    if current_q_index >= len(room["questions"]):
                        await websocket.send_json({"event": "quiz_finished"})
                    else:
                        room["current_state"] = "question_active"
                        next_question = room["questions"][current_q_index]
                        
                        question_payload = {
                            "event": "show_question",
                            "question": {
                                "text": next_question["text"],
                                "options": next_question["options"],
                                "time_limit": next_question["time_limit"]
                            }
                        }
                        
                        await websocket.send_json(question_payload)
                        await manager.broadcast_to_students(room_code, question_payload)

            elif event == "end_game":
                if room:
                    db = SessionLocal()
                    game_session = models.GameSession(quiz_id=quiz_id, room_code=room_code)
                    db.add(game_session)
                    db.commit()
                    db.refresh(game_session)
                    
                    for player_id, student in room["students"].items():
                        history = student.get("history", [])
                        total_correct = sum(1 for ans in history if ans["is_correct"] == 1)
                        
                        result = models.StudentResult(
                            session_id=game_session.id,
                            student_name=student["name"],
                            total_score=student["score"],
                            correct_answers=total_correct,
                            user_id=student.get("user_id")
                        )
                        db.add(result)
                        db.commit()
                        db.refresh(result)
                        
                        for ans in history:
                            student_ans = models.StudentAnswer(
                                result_id=result.id,
                                question_id=ans["question_id"],
                                selected_option=ans["selected_option"],
                                is_correct=ans["is_correct"]
                            )
                            db.add(student_ans)
                    
                    db.commit()
                    final_session_id = game_session.id
                    db.close()
                    
                    # FIX: Broadcast final scores using the same safe mapping technique
                    scores_map = {p_id: s["score"] for p_id, s in room["students"].items()}
                    await manager.broadcast_to_students(room_code, {
                        "event": "game_over",
                        "session_id": final_session_id,
                        "scores": scores_map
                    })
                    
                    await websocket.send_json({
                        "event": "game_over", 
                        "session_id": final_session_id
                    })
                    
                    del manager.active_rooms[room_code]

    except WebSocketDisconnect:
        # --- NEW: Prevent Ghost Players from stalling the host timer ---
        room = manager.active_rooms.get(room_code)
        if room and "host_ws" in room:
            # Recalculate remaining active players and answers
            total_active = len(room["students"])
            current_q_index = room.get("current_question_index", 0)
            answers_in = sum(1 for s in room["students"].values() if s.get("last_answered_index") == current_q_index)
            
            try:
                import asyncio
                # Use asyncio.create_task to safely fire this off while the websocket is closing
                asyncio.create_task(room["host_ws"].send_json({
                    "event": "player_left",
                    "total_players": total_active,
                    "answers_submitted": answers_in
                }))
            except Exception:
                pass


@app.websocket("/ws/student/{room_code}")
async def websocket_student(websocket: WebSocket, room_code: str, student_name: str, token: str = Query(None)):
    
    # 1. Check if they are a logged-in student or a guest
    user_id = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            
            # Briefly open DB to get their actual ID
            db = SessionLocal()
            user = db.query(models.User).filter(models.User.email == email).first()
            if user:
                user_id = user.id
            db.close()
        except Exception:
            pass # If the token is expired/invalid, let them play as a guest

    # 2. Accept connection and add to room
    await websocket.accept()
    player_id = manager.add_student(room_code, student_name, websocket)
    
    if not player_id:
        await websocket.send_json({"error": "Invalid room code or room no longer exists."})
        await websocket.close()
        return

    # 3. Attach the user_id to their live game state
    manager.active_rooms[room_code]["students"][player_id]["user_id"] = user_id
    await websocket.send_json({"event": "join_success", "player_id": player_id})
    host_ws = manager.active_rooms[room_code]["host_ws"]
    await host_ws.send_json({
        "event": "player_joined", 
        "student_name": student_name,
        "total_players": len(manager.active_rooms[room_code]["students"])
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")
            
            if event == "submit_answer":
                room = manager.active_rooms.get(room_code)
                if not room or room["current_state"] != "question_active":
                    continue
                
                student = room["students"][player_id]
                current_q_index = room["current_question_index"]
                
                if student.get("last_answered_index") == current_q_index:
                    continue
                
                selected_option = data.get("selected_option")
                time_remaining_ms = data.get("time_remaining_ms") or 0

                student["last_answered_index"] = current_q_index
                student["last_selected_option"] = selected_option
                
                current_question = room["questions"][current_q_index]
                is_correct = (selected_option == current_question["correct"])
                
                if "history" not in student:
                    student["history"] = []
                
                student["history"].append({
                    "question_id": current_question["id"],
                    "selected_option": selected_option,
                    "is_correct": 1 if is_correct else 0
                })
                
                if is_correct:
                    time_limit_ms = current_question["time_limit"] * 1000
                    speed_bonus = int((time_remaining_ms / time_limit_ms) * 500)
                    student["score"] += 500 + max(0, speed_bonus)
                
                answers_in = sum(1 for s in room["students"].values() if s.get("last_answered_index") == current_q_index)
                
                await host_ws.send_json({
                    "event": "answer_received",
                    "answers_submitted": answers_in,
                    "total_players": len(room["students"])
                })
                
    except WebSocketDisconnect:
        manager.mark_student_offline(room_code, player_id)