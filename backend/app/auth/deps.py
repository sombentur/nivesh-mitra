from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME, find_session
from app.db.base import get_db
from app.db.models import User


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    row = find_session(db, request.cookies.get(COOKIE_NAME), "web")
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    return user
