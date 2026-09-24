from fastapi import APIRouter, Depends

import llm
from dependencies import get_current_user
from models import User
from schemas import AIUsage

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/usage", response_model=AIUsage | None)
def get_ai_usage(current_user: User = Depends(get_current_user)):
    # Limits from the most recent AI answer. None until the first question is
    # asked after the server starts (asking just to check would use up quota).
    return llm.last_usage
