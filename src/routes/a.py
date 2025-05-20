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

        try:
            payload = auth_handler.decode_refresh_token(refresh_token)
            token_id = payload.get('id')
            if token_id:
                redis_db.setex(token_id, 3600, 'locked')  # Lock token for 1 hour
        except Exception:
            pass  # Ignore token decode errors during logout

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