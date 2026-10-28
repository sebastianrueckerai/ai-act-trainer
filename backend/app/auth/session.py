from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import ValidationError

from app.auth.identity import Principal

COOKIE_NAME = "trainer_session"


class SessionCookie:
    def __init__(self, secret_key: str, max_age: int, secure: bool) -> None:
        self.serializer = URLSafeTimedSerializer(secret_key, salt="trainer-session")
        self.max_age = max_age
        self.secure = secure

    def set(self, response: Response, principal: Principal) -> None:
        token = self.serializer.dumps(principal.model_dump())
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=self.max_age,
            httponly=True,
            secure=self.secure,
            samesite="lax",
            path="/",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(COOKIE_NAME, path="/")

    def read(self, request: Request) -> Principal | None:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return None
        try:
            data = self.serializer.loads(token, max_age=self.max_age)
            return Principal.model_validate(data)
        except (BadSignature, SignatureExpired, ValidationError):
            return None
