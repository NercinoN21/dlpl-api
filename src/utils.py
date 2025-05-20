import re
from os import environ, getenv
from platform import system

from dotenv import dotenv_values
from functools import wraps
from fastapi.responses import JSONResponse
from fastapi import status
from typing import Callable, Any


def toggle_environment() -> None:
    """Handle vars according to environment"""
    config = {
        **dotenv_values('.env'),
        **dotenv_values('.env.secrets'),
    }
    if system() == 'Darwin' or config.get('SERVER') == 'local':
        for k, value in config.items():
            environ[k] = value
    if getenv('SERVER') == 'docker':
        for k, value in config.items():
            environ[k] = value
        environ['MONGO_URI'] = 'mongo'
        environ['REDIS_URI'] = 'redis'


def adjust_cpf(cpf: str) -> str:
    adjusted_cpf = re.sub(r'\D', '', cpf)[3:9]
    if len(adjusted_cpf) != 6 or len(cpf) != 14:
        raise ValueError('Invalid CPF, CPF must have the format XXX.XXX.XXX-XX, where X is a digit')
    return adjusted_cpf


def multiple_linear_regression_dlpl(nota_l: float, nota_r: int) -> float:
    return round(
        float(getenv('INTERCEPTOR'))
        + float(getenv('PESO_LINGUAGENS')) * nota_l
        + float(getenv('PESO_REDACAO')) * nota_r,
        2,
    )


def options_discipline(predicted_note: float) -> list[str]:
    return (
        ['Cursar disciplina', 'Dispensa de disciplina']
        if predicted_note >= 6.75
        else ['Cursar disciplina']
    )

def require_active_user(func: Callable[..., Any]):
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any):
        user_data: dict[str, Any] = kwargs.get("user_data", {})

        if not user_data.get('is_active'):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized'},
            )
        return await func(*args, **kwargs)
    return wrapper

def require_admin_active(func: Callable[..., Any]):
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any):
        user_data: dict[str, Any] = kwargs.get("user_data", {})

        if not (user_data.get('is_active') and user_data.get('admin')):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={'detail': 'Unauthorized'},
            )
        return await func(*args, **kwargs)
    return wrapper
