import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth_schemas import LoginRequest
from database import init_database
from dependencies import get_current_user, get_db
from models import User
from routers import ai, chat, documents
from schemas import UserCreate, UserOut
from security import create_access_token, hash_password, verify_password

init_database()

app = FastAPI()

# Websites allowed to call this API from the browser, comma separated.
# Not needed when the frontend and API are served from the same address (Docker setup).
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(ai.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {"message": "AI Document Intelligence API is running"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    # Used by Docker and hosting platforms to check the app is alive
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/users", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()

    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    new_user = User(
        name=user.name, email=user.email, password_hash=hash_password(user.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@app.post("/login")
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "message": "Login successful",
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
    }


@app.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/users", response_model=list[UserOut])
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(User).order_by(User.id).all()
