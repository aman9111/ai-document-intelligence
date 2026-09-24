import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import APIError, RateLimitError
from sqlalchemy.orm import Session

from database import SessionLocal
from dependencies import get_current_user, get_db
from llm import LLMNotConfiguredError, stream_answer
from models import Conversation, Message, User
from routers.documents import find_sources, get_searchable_document, get_user_document, rate_limit_message
from schemas import AIUsage, ChatRequest, ConversationOut, MessageOut

router = APIRouter(tags=["chat"])

# How many earlier messages (user + assistant) the LLM sees, e.g. 6 = last 3 turns.
# More history = better follow-ups but more tokens per question.
HISTORY_MESSAGES = 6


def get_user_conversation(conversation_id: int, user: User, db: Session) -> Conversation:
    conversation = db.get(Conversation, conversation_id)

    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


def sse(event: str, data: dict) -> str:
    # Server-Sent Events format: "event: <name>\ndata: <json>\n\n"
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/documents/{document_id}/conversations", response_model=list[ConversationOut])
def list_conversations(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)

    return (
        db.query(Conversation)
        .filter(Conversation.document_id == document.id, Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_user_conversation(conversation_id, current_user, db).messages


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.delete(get_user_conversation(conversation_id, current_user, db))
    db.commit()


@router.post("/documents/{document_id}/chat")
def chat(
    document_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_searchable_document(document_id, current_user, db)

    if body.conversation_id is None:
        conversation = Conversation(
            user_id=current_user.id,
            document_id=document.id,
            title=body.question[:100],
        )
        db.add(conversation)
        db.flush()  # gives the new conversation its id
    else:
        conversation = get_user_conversation(body.conversation_id, current_user, db)
        if conversation.document_id != document.id:
            raise HTTPException(status_code=400, detail="Conversation belongs to another document")

    history = [
        {"role": message.role, "content": message.content}
        for message in conversation.messages[-HISTORY_MESSAGES:]
    ]

    # A follow-up like "and for how long?" finds nothing on its own, so search
    # with the previous question too ("Which antibiotic was given? and for how long?")
    previous_questions = [m["content"] for m in history if m["role"] == "user"]
    search_query = f"{previous_questions[-1]} {body.question}" if previous_questions else body.question
    sources = find_sources(document, search_query, db)

    db.add(Message(conversation_id=conversation.id, role="user", content=body.question))
    conversation.updated_at = datetime.utcnow()
    db.commit()

    conversation_id = conversation.id

    def event_stream():
        yield sse("start", {"conversation_id": conversation_id})

        parts = []
        usage = None

        try:
            for kind, value in stream_answer(body.question, sources, history):
                if kind == "token":
                    parts.append(value)
                    yield sse("token", {"text": value})
                else:
                    usage = value
        except LLMNotConfiguredError:
            yield sse("error", {"detail": "AI is not configured on the server"})
            return
        except RateLimitError as error:
            yield sse("error", {"detail": rate_limit_message(error)})
            return
        except APIError:
            yield sse("error", {"detail": "The AI service failed. Please try again."})
            return

        # The request's db session is already closed while streaming,
        # so saving the answer needs its own session
        with SessionLocal() as stream_db:
            stream_db.add(
                Message(conversation_id=conversation_id, role="assistant", content="".join(parts).strip())
            )
            stream_db.commit()

        yield sse("done", {"usage": AIUsage.model_validate(usage).model_dump() if usage else None})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # Tell browsers and proxies not to buffer, so each token arrives right away
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
