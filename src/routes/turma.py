"""Import modules"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from src.authentication.main import AuthHandler
from src.databases.main import get_mongodb
from src.schemas.main import TurmaCreateFormData, TurmaUpdateFormData, TurmaDeleteFormData
from src.utils import require_active_user, require_admin_active

mongo_db = Depends(get_mongodb)
auth_handler = AuthHandler()

router = APIRouter(
    prefix='/turma',
    tags=['Turma'],
)

def get_active_semester(db) -> str:
    """Get active semester from config."""
    config = db.config.find_one({}, {'activeSemester': 1})
    if not config or 'activeSemester' not in config:
        raise ValueError('No active semester configured')
    return config['activeSemester']

@router.get('/', name='Get list of classes')
@require_active_user
async def get_turmas(
    request: Request,
    db=mongo_db,
    name: Optional[str] = Query(None, description="Filter classes by name prefix"),
    semester: Optional[str] = Query(None, description="Filter classes by semester"),
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        filter_query = {}
        filter_query['is_active'] = is_active
        if name:
            filter_query['name'] = {'$regex': f'{name}', '$options': 'i'}
        if semester:
            filter_query['semester'] = semester
        
        values = list(db.turma.find(
            filter_query,
            {'_id': 0, 'name': 1, 'semester': 1}
        ))

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'count': len(values), 'turmas': values},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.get('/active', name='Get classes of active semester of config')
async def get_active_turmas(
    request: Request,
    db=mongo_db,
) -> JSONResponse:
    try:
        semester = get_active_semester(db)
        
        filter_query = {
            'semester': semester,
            'is_active': True
        }

        values = list(db.turma.find(
            filter_query,
            {'_id': 0, 'name': 1, 'semester': 1}
        ))

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'count': len(values), 'turmas': values},
            headers={'x-forwarded-for': request.client.host},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': str(e)},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.get('/semesters', name='Get unique semesters')
@require_active_user
async def get_semesters(
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        semesters = db.turma.distinct('semester')
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'semesters': sorted(semesters)},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.post('/', name='Create new class')
@require_active_user
async def create_turma(
    data: TurmaCreateFormData,
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        existing_turma = db.turma.find_one({
            'name': data.name,
            'semester': data.semester,
            'is_active': True
        })
        
        if existing_turma:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={'detail': 'Class already exists for this semester'},
                headers={'x-forwarded-for': request.client.host},
            )

        turma_data = {
            'name': data.name,
            'semester': data.semester,
            'is_active': True,
            'created_at': datetime.now(timezone.utc),
        }
        
        result = db.turma.insert_one(turma_data)
        
        if result.inserted_id:
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={'detail': 'Class created successfully'},
                headers={'x-forwarded-for': request.client.host},
            )
            
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={'detail': 'Failed to create class'},
            headers={'x-forwarded-for': request.client.host},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': str(e)},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.put('/', name='Update class')
@require_active_user
async def update_turma(
    data: TurmaUpdateFormData,
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        existing_turma = db.turma.find_one({
            'name': data.name,
            'semester': data.semester
        })
        
        if not existing_turma:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'detail': 'Class not found'},
                headers={'x-forwarded-for': request.client.host},
            )

        if data.new_name or data.new_semester:
            new_name = data.new_name if data.new_name else data.name
            new_semester = data.new_semester if data.new_semester else data.semester
            
            existing_with_new = db.turma.find_one({
                'name': new_name,
                'semester': new_semester,
                '_id': {'$ne': existing_turma['_id']}
            })
            
            if existing_with_new:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={'detail': 'Class already exists with this name and semester'},
                    headers={'x-forwarded-for': request.client.host},
                )

        update_data = {
            'updated_at': datetime.now(timezone.utc)
        }
        
        if data.new_name:
            update_data['name'] = data.new_name
        if data.new_semester:
            update_data['semester'] = data.new_semester

        result = db.turma.update_one(
            {'name': data.name, 'semester': data.semester},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={'detail': 'Class updated successfully'},
                headers={'x-forwarded-for': request.client.host},
            )
            
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={'detail': 'Failed to update class'},
            headers={'x-forwarded-for': request.client.host},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': str(e)},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.delete('/', name='Delete class')
@require_admin_active
async def delete_turma(
    data: TurmaDeleteFormData,
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        existing_turma = db.turma.find_one({
            'name': data.name,
            'semester': data.semester,
            'is_active': True
        })
        
        if not existing_turma:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'detail': 'Class not found'},
                headers={'x-forwarded-for': request.client.host},
            )

        result = db.turma.update_one(
            {'name': data.name, 'semester': data.semester},
            {'$set': {'is_active': False}}
        )
        
        if result.modified_count > 0:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={'detail': 'Class deleted successfully'},
                headers={'x-forwarded-for': request.client.host},
            )
            
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={'detail': 'Failed to delete class'},
            headers={'x-forwarded-for': request.client.host},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': str(e)},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e
