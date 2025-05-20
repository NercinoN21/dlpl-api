from datetime import datetime, timedelta, timezone
from os import getenv
from uuid import uuid4

import jwt
from bcrypt import checkpw
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.databases.main import get_redis


class AuthHandler:
    security = HTTPBearer(description='Bearer token')
    redis_db = get_redis()

    def __init__(self) -> None:
        self.pwd_context = None
        self.secret = getenv('JWT_SECRET_KEY')

    def verify_password(
        self, plain_password: str, hashed_password: str
    ) -> str:
        self.pwd_context = checkpw(
            str.encode(plain_password), str.encode(hashed_password)
        )
        return self.pwd_context

    def encode_token(self, user_data: dict, type: str) -> str:
        payload = dict(
            id=uuid4().hex,
            admin=user_data.get('admin', False),
            is_active=user_data.get('is_active', False),
            sub=user_data.get('id'),
            name=user_data.get('name'),
        )
        to_encode = payload.copy()
        if type == 'access_token':
            to_encode.update(
                {
                    'exp': datetime.now(timezone.utc) + timedelta(minutes=60),
                    'refresh': False,
                }
            )
        else:
            to_encode.update(
                {
                    'exp': datetime.now(timezone.utc) + timedelta(hours=720),
                    'refresh': True,
                }
            )

        return jwt.encode(to_encode, self.secret, algorithm='HS256')

    def encode_login_token(self, user_data: dict) -> tuple:
        pattern = f"token:*"
        for key in self.redis_db.scan_iter(match=pattern):
            value = self.redis_db.get(key)
            if value and value.decode('utf-8').startswith(f"{user_data.get('id')}:"):
                self.redis_db.delete(key)

        access_token = self.encode_token(user_data, 'access_token')
        refresh_token = self.encode_token(user_data, 'refresh_token')
        return access_token, refresh_token

    def decode_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret, algorithms=['HS256'])
            if 'sub' not in payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Invalid token',
                )
            if payload['refresh'] == True:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Invalid token',
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Signature has expired',
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid token',
            )

    def decode_refresh_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret, algorithms=['HS256'])
            if 'sub' not in payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Invalid token',
                )
            if payload['refresh'] == False:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Invalid token',
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Signature has expired',
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid token',
            )

    def lock_refresh_token(self, token: str, redis_db=redis_db) -> str:
        payload = self.decode_refresh_token(token)
        token_id = payload.get('id')
        user_id = payload.get('sub')
        expiration = payload.get('exp')
        is_active = payload.get('is_active')
        if not user_id or not token_id or not expiration or not is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid token',
            )
        ttl = datetime.fromtimestamp(expiration) - datetime.now()
        ttl = int(ttl.total_seconds())
        redis_db.setex(f"token:{token_id}", ttl, f"{user_id}:{is_active}")
        return user_id

    def verify_refresh_token(self, token: str, redis_db=redis_db) -> None:
        payload = self.decode_refresh_token(token)
        token_id = payload.get('id')
        if not token_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid token',
            )
        locked = redis_db.get(f"token:{token_id}")
        if locked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Token locked'
            )

    def auth_user(
        self,
        request: Request,
        auth: HTTPAuthorizationCredentials = Security(security),
    ) -> bool:
        token = request.cookies.get('session-token')
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token not found',
            )
        self.verify_refresh_token(token)
        return self.decode_access_token(auth.credentials)
