"""Import modules"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.authentication.main import AuthHandler
from src.databases.main import get_mongodb
from src.schemas.main import ConfigCreateUpdateFormData
from src.utils import require_admin_active

mongo_db = Depends(get_mongodb)
auth_handler = AuthHandler()

router = APIRouter(
    prefix='/config',
    tags=['Config'],
)

def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC if it has timezone info, otherwise assume it's UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def validate_dates(start_date: datetime, end_date: datetime) -> None:
    """Validate enrollment dates."""
    start_date = to_utc(start_date)
    end_date = to_utc(end_date)
    
    if end_date <= start_date:
        raise ValueError(
            f'A data de início ({start_date.strftime("%d/%m/%Y %H:%M")}) '
            f'deve ser anterior à data de término ({end_date.strftime("%d/%m/%Y %H:%M")})'
        )
    
    min_end_date = start_date + timedelta(hours=1)
    if end_date < min_end_date:
        raise ValueError(
            f'A data de término ({end_date.strftime("%d/%m/%Y %H:%M")}) '
            f'deve ser pelo menos 1 hora após a data de início ({start_date.strftime("%d/%m/%Y %H:%M")})'
        )

@router.get('/', name='Get configuration')
async def get_config(
    request: Request,
    db=mongo_db
) -> JSONResponse:
    try:
        config = db.config.find_one({}, {'_id': 0})
        
        if not config:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'detail': 'Configuration not found'},
                headers={'x-forwarded-for': request.client.host},
            )

        for field in ['enrollmentStartDate', 'enrollmentEndDate', 'created_at', 'updated_at']:
            if config.get(field):
                config[field] = config[field].isoformat()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=config,
            headers={'x-forwarded-for': request.client.host},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Internal server error: {str(e)}',
        ) from e

@router.post('/', name='Create or update configuration')
@require_admin_active
async def create_config(
    data: ConfigCreateUpdateFormData,
    request: Request,
    db=mongo_db,
    user_data=Depends(auth_handler.auth_user),
) -> JSONResponse:
    try:
        current_config = db.config.find_one({})
        now = datetime.now(timezone.utc)
        
        validate_dates(data.enrollmentStartDate, data.enrollmentEndDate)
        
        update_data = {
            'activeSemester': data.activeSemester,
            'enrollmentStartDate': to_utc(data.enrollmentStartDate),
            'enrollmentEndDate': to_utc(data.enrollmentEndDate),
            'updated_at': now
        }
        
        if not current_config:
            update_data['created_at'] = now
        
        result = db.config.find_one_and_update(
            {},
            {'$set': update_data},
            upsert=True,
            return_document=True
        )
        
        if not result:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={'detail': 'Failed to create/update configuration'},
                headers={'x-forwarded-for': request.client.host},
            )
            
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'detail': 'Configuration created/updated successfully'},
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

