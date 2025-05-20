"""Import modules"""
from datetime import datetime, timezone
from typing import Optional
from os import getenv

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Form, Request, Response, status, Query
from fastapi.responses import JSONResponse
from typing_extensions import Annotated
from bcrypt import hashpw, gensalt

from src.authentication.main import AuthHandler
from src.databases.main import get_mongodb, get_redis
from src.schemas.main import (
    UserLoginFormData,
    UserRegistrationFormData,
    UserUpdateActiveFormData,
    UserUpdateAdminFormData,
    UserUpdateFormData
)
from src.utils import require_active_user, require_admin_active

mongo_db = Depends(get_mongodb)
redis_db = Depends(get_redis)
auth_handler = AuthHandler()

router = APIRouter(
    prefix='/users',
    tags=['Users'],
)

def create_default_admin(db) -> bool:
    """Create default admin user if no users exist."""
    if db.users.count_documents({}) == 0:
        default_password = getenv('DEFAULT_ADMIN_PASSWORD', '!admin-dlplUFPB-2025!')
        hashed_password = hashpw(default_password.encode('utf-8'), gensalt()).decode('utf-8')

        db.users.insert_one({
            'name': 'admin',
            'password': hashed_password,
            'created_at': datetime.now(timezone.utc),
            'is_active': True,
            'admin': True,
            'otp_secret': None
        })

        return True
    return False

@router.post('/setup', name='Setup initial admin user')
async def setup_admin(
    db=mongo_db
) -> JSONResponse:
    try:
        if create_default_admin(db):
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    'detail': 'Setup completed successfully',
                    'warning': 'IMPORTANT: Please change the default admin password immediately after first login for security reasons.'
                }
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'detail': 'Setup not needed, users already exist'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.post('/login', name='Perform user authentication')
async def login_user(
    response: Response,
    data: Annotated[UserLoginFormData, Form()],
    db=mongo_db
) -> dict[str, str]:
    try:
        user = db.users.find_one(
            {'name': data.name, 'is_active': True},
            {'_id': True, 'password': True, 'name': True, 'admin': True, 'is_active': True}
        )

        if not user:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={'detail': 'User not found'}
            )

        if not auth_handler.verify_password(data.password, user['password']):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={'detail': 'Username or password not valid'}
            )

        payload = {
            'name': user['name'],
            'id': str(user['_id']),
            'admin': user['admin'],
            'is_active': user['is_active']
        }

        access_token, refresh_token = auth_handler.encode_login_token(payload)
        response.set_cookie(key='session-token',
                            value=refresh_token, httponly=True)
        response.status_code = status.HTTP_201_CREATED
        response.media_type = "application/json"

        return {'token': access_token}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.patch('/login', name='Refresh user authentication')
async def refresh_login_user(
    request: Request,
    db=mongo_db,
    redis_db=redis_db
) -> JSONResponse:
    try:
        refresh_token = request.cookies.get('session-token')
        if not refresh_token:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized'}
            )

        payload = auth_handler.decode_refresh_token(refresh_token)
        user_id = payload.get('sub')
        token_id = payload.get('id')

        if not user_id or not token_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized - bad request'}
            )

        if redis_db.get(token_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized - locked list'}
            )

        user = db.users.find_one(
            {'_id': ObjectId(user_id), 'is_active': True},
            {'_id': True, 'name': True, 'admin': True, 'is_active': True}
        )

        if not user:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized - invalid user'}
            )

        payload = {
            'name': user['name'],
            'id': str(user['_id']),
            'admin': user['admin'],
            'is_active': user['is_active']
        }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'token': auth_handler.encode_token(payload, 'access_token')}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.post('/logout', name='Perform user logout')
async def logout_user(
    request: Request,
    response: Response,
    db=mongo_db
) -> JSONResponse:
    try:
        refresh_token = request.cookies.get('session-token')
        if not refresh_token:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'User is already logout'}
            )

        user_id = auth_handler.lock_refresh_token(refresh_token)
        user = db.users.find_one(
            {'_id': ObjectId(user_id), 'is_active': True},
            {'_id': True}
        )

        if not user:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized - invalid user'}
            )

        response.delete_cookie('session-token')
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'detail': 'User logout successfully'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.get('/', name='Get list of users')
@require_active_user
async def get_users(
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
    name: Optional[str] = Query(None, description="Filter users by name (case-insensitive)"),
    is_active: Optional[bool] = Query(True, description="Filter users by active status")
) -> JSONResponse:
    try:
        match_stage = {'is_active': is_active}
        if name:
            match_stage['name'] = {'$regex': f'{name}', '$options': 'i'}

        pipeline = [
            {
                '$project': {
                    '_id': False,
                    'name': True,
                    'is_active': True,
                    'admin': True
                }
            },
            {'$match': match_stage}
        ]

        users = list(db.users.aggregate(pipeline))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'count': len(users), 'users': users}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.post('/', name='Register new user')
@require_admin_active
async def add_user(
    data: Annotated[UserRegistrationFormData, Form()],
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user)
) -> JSONResponse:
    try:
        if db.users.find_one({'name': data.name}):
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={'detail': 'User already exists'}
            )

        user_data = {
            'name': data.name,
            'password': data.password,
            'created_at': datetime.now(timezone.utc),
            'is_active': True,
            'admin': False,
            'otp_secret': data._otp_secret
        }

        result = db.users.insert_one(user_data)
        if not result.inserted_id:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={'detail': 'Failed to create user'}
            )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={'detail': 'User created successfully'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.put('/update-admin', name='Update user admin status')
@require_admin_active
async def update_user_admin(
    data: Annotated[UserUpdateAdminFormData, Form()],
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user)
) -> JSONResponse:
    try:
        if not db.users.find_one({'name': data.name}):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'detail': 'User not found'}
            )

        db.users.update_one(
            {'name': data.name},
            {
                '$set': {
                    'admin': data.admin,
                    'updated_at': datetime.now(timezone.utc)
                }
            }
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'detail': 'User updated successfully'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.put('/update-active', name='Update user active status')
@require_admin_active
async def update_user_active(
    data: Annotated[UserUpdateActiveFormData, Form()],
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user)
) -> JSONResponse:
    try:
        if not db.users.find_one({'name': data.name}):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'detail': 'User not found'}
            )

        db.users.update_one(
            {'name': data.name},
            {
                '$set': {
                    'is_active': data.is_active,
                    'updated_at': datetime.now(timezone.utc)
                }
            }
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'detail': 'User updated successfully'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e

@router.put('/', name='Update user')
@require_active_user
async def update_user(
    data: Annotated[UserUpdateFormData, Form()],
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user)
) -> JSONResponse:
    try:
        user = db.users.find_one({'name': data.name})
        if not user:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'detail': 'User not found'}
            )

        if user_data['name'] != data.name and not user_data['admin']:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized'}
            )

        if data.new_name and db.users.find_one({'name': data.new_name}):
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={'detail': 'User already exists'}
            )

        update_data = {}
        if data.new_name:
            update_data['name'] = data.new_name
        if data.new_password:
            update_data['password'] = data.new_password
        update_data['updated_at'] = datetime.now(timezone.utc)

        db.users.update_one(
            {'name': data.name},
            {'$set': update_data}
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'detail': 'User updated successfully'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}'
        ) from e