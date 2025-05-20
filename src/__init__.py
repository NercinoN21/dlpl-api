from src.utils import toggle_environment

# Load env variables
toggle_environment()

from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.authentication.main import AuthHandler
from src.routes import enrollment, users, turma, config

app = FastAPI()
auth_handler = AuthHandler()

# Mount static directory
app.mount('/static', StaticFiles(directory='static'), name='static')

# Middleware
@app.middleware('http')
async def add_process_time_header(request: Request, call_next):
    """Middleware for response headers and logging"""
    response = await call_next(request)
    refresh_token = request.cookies.get('session-token')
    if refresh_token:
        try:
            payload = auth_handler.decode_refresh_token(refresh_token)
            d = datetime.fromtimestamp(payload.get('exp'))

            diff_time = (
                datetime.fromtimestamp(payload.get('exp')) - datetime.now()
            )
            # print(payload, diff_time)
        except Exception as e:
            pass
    return response


@app.get(path='/', include_in_schema=False)
async def swagger():
    """Redirect to Swagger Docs"""
    return RedirectResponse('/swagger')


@app.get(
    path='/swagger',
    include_in_schema=False,
)
async def docs():
    """Render Swagger Docs"""
    return get_swagger_ui_html(
        openapi_url='/openapi.json',
        title='API ODSR - Swagger Docs',
        swagger_favicon_url='/static/favicon.ico',
        swagger_ui_parameters={'description': 'Documentation'},
    )


@app.get(
    path='/redoc',
    include_in_schema=False,
)
async def redocs():
    """Render ReDoc Docs"""
    return get_redoc_html(
        openapi_url='/openapi.json',
        title='API ODSR - ReDoc',
        redoc_favicon_url='/static/favicon.ico',
    )


# include routers
app.include_router(enrollment.router)
app.include_router(users.router)
app.include_router(turma.router)
app.include_router(config.router)