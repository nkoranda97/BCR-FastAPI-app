from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from itsdangerous import URLSafeSerializer
from typing import Optional, Dict, Any
import json
from starlette.datastructures import MutableHeaders


class SessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.serializer = URLSafeSerializer(secret_key)
        self.session_cookie = "session"

    async def dispatch(self, request: Request, call_next):
        # Get session data from cookie
        session_data = self._get_session_data(request)

        # Store session data in request state instead of directly on request
        request.state.session = session_data

        # Process the request
        response = await call_next(request)

        # Save session data to cookie
        if hasattr(request.state, "session"):
            self._set_session_data(response, request.state.session)

        return response

    def _get_session_data(self, request: Request) -> Dict[str, Any]:
        session_cookie = request.cookies.get(self.session_cookie)
        if session_cookie:
            try:
                return json.loads(self.serializer.loads(session_cookie))
            except:
                return {}
        return {}

    def _set_session_data(self, response: Response, session_data: Dict[str, Any]):
        if session_data:
            cookie_value = self.serializer.dumps(json.dumps(session_data))
            response.set_cookie(
                self.session_cookie,
                cookie_value,
                httponly=True,
                samesite="lax",
                max_age=3600,  # 1 hour
            )
        else:
            response.delete_cookie(self.session_cookie)
