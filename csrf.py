from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from itsdangerous import URLSafeTimedSerializer
import os
import base64
from typing import Optional
from fastapi.responses import JSONResponse

class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.serializer = URLSafeTimedSerializer(secret_key)
        self.csrf_token_name = "csrf_token"
        self.csrf_header_name = "X-CSRF-Token"

    async def dispatch(self, request: Request, call_next):
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            # Generate new CSRF token for GET requests
            token = self._generate_token()
            response = await call_next(request)
            response.set_cookie(
                key=self.csrf_token_name,
                value=token,
                httponly=True,
                samesite="Lax",
                secure=os.getenv("ENVIRONMENT") == "production"
            )
            return response

        # For POST/PUT/DELETE requests, verify CSRF token
        if request.method in ["POST", "PUT", "DELETE"]:
            token = request.cookies.get(self.csrf_token_name)
            header_token = request.headers.get(self.csrf_header_name)

            if not token or not header_token or token != header_token:
                if request.headers.get("accept") == "application/json":
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF token validation failed"}
                    )
                raise HTTPException(status_code=403, detail="CSRF token validation failed")

        response = await call_next(request)
        return response

    def _generate_token(self) -> str:
        # Generate random bytes and encode them to base64
        random_bytes = os.urandom(32)
        encoded_bytes = base64.b64encode(random_bytes).decode('utf-8')
        return self.serializer.dumps(encoded_bytes)

def get_csrf_token(request: Request) -> Optional[str]:
    """Get CSRF token from request cookies"""
    return request.cookies.get("csrf_token") 