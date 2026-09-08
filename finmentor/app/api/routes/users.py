"""users routes (spec section 22): POST /api/users, GET /api/users/{id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.repositories import users as users_repo
from app.schemas.user import UserIn, UserOut

router = APIRouter(prefix="/api", tags=["users"])


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserIn, db: DbSession) -> UserOut:
    if users_repo.get_by_telegram_id(db, payload.telegram_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a user with this telegram_id already exists",
        )
    user = users_repo.create(db, telegram_id=payload.telegram_id, locale=payload.locale)
    db.commit()
    return UserOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: DbSession) -> UserOut:
    user = users_repo.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return UserOut.model_validate(user)
