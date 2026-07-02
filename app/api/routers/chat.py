# app/api/routers/chat.py

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    ConversationOut,
    ConversationCreate,
    MoodRequest,
    MoodResponse,
    ProgressDay,
    DeleteResponse,
)
from app.auth.dependencies import get_current_user_id
from app.api.dependencies import get_chat_service
from app.services.chat_service import ChatService


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    result = await chat_service.ask(
        user_id,
        data.message,
        conversation_id=data.conversation_id,
    )
    return ChatResponse(**result)


# -----------------------------------------------------
# Conversaciones
# -----------------------------------------------------

@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    data: ConversationCreate,
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    conversation_id = await chat_service.memory.create_conversation(
        user_id, data.title
    )
    conversation = await chat_service.memory.get_conversation(conversation_id, user_id)
    return ConversationOut(
        id=str(conversation["_id"]),
        title=conversation["title"],
        created_at=conversation["created_at"],
        last_message_at=conversation["last_message_at"],
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.list_conversations(user_id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    before: float | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    messages = await chat_service.get_conversation_messages(
        user_id, conversation_id, limit=limit, before=before
    )

    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada",
        )

    return [MessageOut(**m) for m in messages]


@router.delete("/conversations/{conversation_id}", response_model=DeleteResponse)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    deleted = await chat_service.delete_conversation(user_id, conversation_id)
    return DeleteResponse(deleted=deleted)


# -----------------------------------------------------
# Mood manual
# -----------------------------------------------------

@router.post("/mood", response_model=MoodResponse)
async def log_mood(
    data: MoodRequest,
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    logged_as = await chat_service.log_mood(user_id, data.mood)
    return MoodResponse(logged_as=logged_as)


# -----------------------------------------------------
# Progreso
# -----------------------------------------------------

@router.get("/progress", response_model=list[ProgressDay])
async def get_progress(
    days: int = Query(default=14, ge=1, le=90),
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    trend = await chat_service.get_emotion_trend(user_id, days=days)
    return [ProgressDay(**d) for d in trend]


# -----------------------------------------------------
# Perfil
# -----------------------------------------------------

@router.get("/profile")
async def get_profile(
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.get_profile(user_id)


@router.delete("/profile", response_model=DeleteResponse)
async def delete_profile(
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
):
    deleted = await chat_service.delete_user_data(user_id)
    return DeleteResponse(deleted=deleted)
