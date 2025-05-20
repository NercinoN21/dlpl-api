"""Import modules"""
from datetime import datetime, timezone
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
import json
from typing_extensions import Annotated

from src.authentication.main import AuthHandler
from src.databases.main import get_mongodb, get_redis, with_mongodb
from src.schemas.main import (
    EnrollmentCreateFormData,
    EnrollmentUpdateFormData,
    EnrollmentDeleteFormData
)
from src.utils import (
    multiple_linear_regression_dlpl,
    options_discipline,
    require_active_user,
    require_admin_active,
    adjust_cpf
)
import math

from src.routes.turma import get_active_turmas

mongo_db = Depends(get_mongodb)
redis_db = Depends(get_redis)
auth_handler = AuthHandler()

router = APIRouter(
    prefix='/enrollment',
    tags=['Enrollment'],
)

@router.get('/names', name='Get all names')
async def get_names(
    request: Request,
    db=mongo_db,
    redis=redis_db,
    query_name: str = Query(None, description='Filter by name'),
) -> JSONResponse:
    try:
        cache_key = f"names:{query_name if query_name else 'all'}"

        cached_data = redis.get(cache_key)
        if cached_data:
            return json.loads(cached_data)

        filter_query = {}
        if query_name:
            filter_query = {
                'INSCRITO': {'$regex': re.escape(query_name), '$options': 'i'}
            }

        results = db.sisu.find(
            filter_query,
            {'_id': 0, 'INSCRITO': 1},
        ).limit(100)

        names = [row['INSCRITO'] for row in results]

        redis.setex(
            cache_key,
            3600,
            json.dumps(names)
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=names,
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.get('/verify-cpf-by-name', name='Verify CPF by name')
async def verify_cpf_by_name(
    name: str,
    cpf: str,
    request: Request,
    db=mongo_db
) -> JSONResponse:
    try:
        cpf = adjust_cpf(cpf)
        data = db.sisu.find(
            {'INSCRITO': name},
            {'_id': 0, 'CPF': 1},
        )
        cpfs_masked = [row['CPF'] for row in data]

        if not cpf in cpfs_masked:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'message': 'CPF not found for this name'},
                headers={'x-forwarded-for': request.client.host},
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'message': 'CPF found for this name'},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.get('/courses', name='Get courses by name and CPF')
async def get_courses_by_name_and_cpf(
    name: str,
    cpf: str,
    request: Request,
    db=mongo_db
) -> JSONResponse:
    try:
        cpf = adjust_cpf(cpf)
        data = db.sisu.find(
            {'INSCRITO': name, 'CPF': cpf},
            {'_id': 0, 'CURSO': 1},
        )
        courses = [row['CURSO'] for row in data]

        if not courses:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'message': 'No course found for this name and CPF'},
                headers={'x-forwarded-for': request.client.host},
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'courses': courses},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.get('/entry-info', name='Get entry info by name, CPF and course')
async def get_entry_info_by_name_cpf_course(
    name: str,
    cpf: str,
    course: str,
    request: Request,
    db=mongo_db,
) -> JSONResponse:
    try:
        cpf = adjust_cpf(cpf)
        data = list(
            db.sisu.find(
                {'INSCRITO': name, 'CPF': cpf, 'CURSO': course},
                {'_id': 0, 'NOTA_L': 1, 'NOTA_R': 1, 'ANO': 1},
            )
            .sort([('ANO', -1)])
            .limit(1)
        )

        if not data:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'message': 'No entry info found for this name, CPF and course'},
                headers={'x-forwarded-for': request.client.host},
            )

        data = data[0]
        data['ANO_INGRESSO'] = data.pop('ANO')
        data['NOTA_PREDITA'] = multiple_linear_regression_dlpl(
            nota_l=data['NOTA_L'],
            nota_r=data['NOTA_R'],
        )
        data['OPCOES'] = options_discipline(data['NOTA_PREDITA'])
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=data,
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.post('/', name='Create enrollment')
async def create_enrollment(
    data: EnrollmentCreateFormData,
    request: Request,
    db=mongo_db,
) -> JSONResponse:
    try:
        info = await get_entry_info_by_name_cpf_course(
            data.name,
            f'000.{data.cpf[:3]}.{data.cpf[3:]}-00', # To pass the verification
            data.course,
            request=request,
            db=db
        )

        if info.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='No entry info found for this name, CPF and course',
            )

        info = eval(info.body)

        if data.choice not in info['OPCOES']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Invalid choice',
            )

        active_turmas = await get_active_turmas(
            request=request,
            db=db
        )
        if {'name': data.turma, 'semester': data.semester} not in eval(active_turmas.body)['turmas']:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Class not found for this semester',
            )

        if db.enrollment.find_one({'INSCRITO': data.name, 'CPF_MASKED': data.cpf, 'CURSO': data.course, 'SEMESTRE': data.semester, 'IS_ACTIVE': True}) is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Enrollment already exists',
            )

        enrollment_data = {
            'DATA_INSCRICAO': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'INSCRITO': data.name,
            'CPF_MASKED': data.cpf,
            'CURSO': data.course,
            'ESCOLHA': data.choice,
            'TURMA': data.turma,
            'SEMESTRE': data.semester,
            'IS_ACTIVE': True,
        }

        db.enrollment.insert_one(enrollment_data)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={'message': 'Enrollment created successfully'},
            headers={'x-forwarded-for': request.client.host},
        )
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={'detail': e.detail},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.get('/', name='Get all enrollments')
@require_active_user
async def get_enrollments(
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
    query_semestre: str = Query(None, description='Filter by semester'),
    query_curso_aluno: str = Query(None, description='Filter by student course'),
    query_nome_aluno: str = Query(None, description='Filter by student name'),
    query_nome_turma: str = Query(None, description='Filter by class name'),
    query_escolha: str = Query(None, description='Filter by choice'),
    query_is_active: Optional[bool] = Query(True, description='Filter by active status'),
    page: int = Query(1, ge=1, description='Page number'),
    page_size: int = Query(10, ge=1, le=100, description='Number of items per page'),
) -> JSONResponse:
    try:
        filter_query = {}

        if query_semestre:
            filter_query['SEMESTRE'] = query_semestre
        if query_curso_aluno:
            filter_query['CURSO'] = {'$regex': re.escape(query_curso_aluno), '$options': 'i'}
        if query_nome_aluno:
            filter_query['INSCRITO'] = {'$regex': re.escape(query_nome_aluno), '$options': 'i'}
        if query_nome_turma:
            filter_query['TURMA'] = {'$regex': re.escape(query_nome_turma), '$options': 'i'}
        if query_escolha:
            filter_query['ESCOLHA'] = query_escolha

        filter_query['IS_ACTIVE'] = query_is_active

        total_documents = db.enrollment.count_documents(filter_query)
        skip = (page - 1) * page_size
        limit = page_size
        data = list(
            db.enrollment.find(
                filter_query,
                {'_id': 0},
            )
            .skip(skip)
            .limit(limit)
        )
        total_pages = math.ceil(total_documents / page_size)


        response_content = {
            "data": data,
            "pagination": {
                "total_documents": total_documents,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "has_next_page": page < total_pages,
                "has_prev_page": page > 1
            }
        }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_content,
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.put('/', name='Update enrollment')
@require_active_user
async def update_enrollment(
    data: EnrollmentUpdateFormData,
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:

        if db.enrollment.find_one({'INSCRITO': data.name, 'CPF_MASKED': data.cpf, 'CURSO': data.course, 'SEMESTRE': data.semester, 'IS_ACTIVE': True}) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Enrollment not found',
            )

        if data.new_turma and data.new_semestre:
            active_turmas = await get_active_turmas(
                request=request,
                db=db
            )
            if {'name': data.new_turma, 'semester': data.new_semestre} not in eval(active_turmas.body)['turmas']:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='Class not found for this semester',
                )

        if data.new_choice:
            info = await get_entry_info_by_name_cpf_course(
                data.name,
                f'000.{data.cpf[:3]}.{data.cpf[3:]}-00',  # To pass the verification
                data.course,
                request=request,
                db=db
            )
            if 'body' not in info.__dict__.keys():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='No entry info found for this name, CPF and course',
                )
            info = eval(info.body)
            if data.new_choice not in info['OPCOES']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Invalid choice',
                )

        filter_query = {
            'INSCRITO': data.name,
            'CPF_MASKED': data.cpf,
            'CURSO': data.course,
            'SEMESTRE': data.semester,
            'IS_ACTIVE': True,
        }

        update_data = {}
        if data.new_semestre and data.new_semestre:
            update_data['SEMESTRE'] = data.new_semestre
            update_data['TURMA'] = data.new_turma
        if data.new_choice:
            update_data['ESCOLHA'] = data.new_choice

        db.enrollment.update_one(filter_query, {'$set': update_data})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'message': 'Enrollment updated successfully'},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.delete('/', name='Delete enrollment')
@require_admin_active
async def delete_enrollment(
    data: EnrollmentDeleteFormData,
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        if db.enrollment.find_one({'INSCRITO': data.name, 'CPF_MASKED': data.cpf, 'CURSO': data.course, 'SEMESTRE': data.semester, 'IS_ACTIVE': True}) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Enrollment not found',
            )

        filter_query = {
            'INSCRITO': data.name,
            'CPF_MASKED': data.cpf,
            'CURSO': data.course,
            'SEMESTRE': data.semester,
            'IS_ACTIVE': True,
        }

        update_data = {
            'IS_ACTIVE': False,
        }

        db.enrollment.update_one(filter_query, {'$set': update_data})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'message': 'Enrollment deleted successfully'},
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e
