# app/schemas/chat.py

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    is_crisis_response: bool = False
    conversation_id: str


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: float


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: float
    last_message_at: float


class ConversationCreate(BaseModel):
    title: str = "Nueva conversación"


class MoodRequest(BaseModel):
    mood: str  # "triste" | "ansioso" | "enojado" | "perdido" | "bien"


class MoodResponse(BaseModel):
    logged_as: str


class ProgressDay(BaseModel):
    date: str
    counts: dict[str, int]


class DeleteResponse(BaseModel):
    deleted: bool
