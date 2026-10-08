from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)

class StaffAdd(BaseModel):
    email: str

class UserResponse(BaseModel):
    id: int
    email: str
    is_professor: bool

    class Config:
        from_attributes = True

# --- Questions ---
class QuestionBase(BaseModel):
    text: str
    option_red: str
    option_blue: str
    option_yellow: str
    option_green: str
    correct_option: str
    # None means no timer for this question
    time_limit_seconds: Optional[int] = 15
    explanation: Optional[str] = None

class QuestionCreate(QuestionBase):
    pass

class Question(QuestionBase):
    id: int
    quiz_id: int

    class Config:
        from_attributes = True  # Tells Pydantic to read data from SQLAlchemy models

# --- Quizzes ---
class QuizBase(BaseModel):
    title: str
    use_timer: bool = True
    auto_advance_results: bool = True

class QuizCreate(QuizBase):
    pass

class Quiz(QuizBase):
    id: int
    owner_id: int
    questions: List[Question] = []

    class Config:
        from_attributes = True

# --- Full quiz payload (visual builder, JSON upload and edit share this) ---
class QuestionBuilderItem(BaseModel):
    text: str = Field(min_length=1)
    option_red: str = Field(min_length=1)
    option_blue: str = Field(min_length=1)
    option_yellow: str = Field(min_length=1)
    option_green: str = Field(min_length=1)
    correct_option: Literal["red", "blue", "yellow", "green"]
    # null = no timer for this question
    time_limit_seconds: Optional[int] = Field(default=15, ge=5, le=120)
    explanation: Optional[str] = ""

class FullQuizPayload(BaseModel):
    title: str = Field(min_length=1)
    # false = no question in the quiz is timed, whatever its own time limit says
    use_timer: bool = True
    # false = after every question the results wait for the professor's "Next Question"
    auto_advance_results: bool = True
    questions: List[QuestionBuilderItem] = Field(min_length=1)

class GoogleAuthRequest(BaseModel):
    token: str
