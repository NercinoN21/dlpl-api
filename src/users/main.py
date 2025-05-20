from base64 import b64encode
from io import BytesIO
from os import getenv

import pyotp
from itsdangerous.exc import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer
from pyotp.totp import TOTP
from qrcode import QRCode


class UserHandler:
    def __init__(self) -> None:
        self.app_secret = getenv('APP_SECRET_KEY')
        self.app_name = getenv('FRONTEND_APP_NAME')

    def __qr_image(self, uri: str) -> str:
        """Gera um QR Code base64 para autenticação OTP."""
        qr = QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buffered = BytesIO()
        img.save(buffered)
        return b64encode(buffered.getvalue()).decode('utf-8')

    def create_otp_token(self, secret: str, username: str) -> str:
        """Cria um token OTP baseado no nome de usuário."""
        uri = TOTP(secret).provisioning_uri(
            name=username, issuer_name=self.app_name
        )
        return self.__qr_image(uri)

    def verify_otp_pin(self, secret: str, otp_code: str) -> bool:
        """Verifica se o código OTP digitado é válido."""
        totp = TOTP(secret)
        return totp.verify(otp_code)

    def create_session_token(self, username: str) -> str:
        """Cria um token de sessão assinado, para login do usuário."""
        try:
            s = URLSafeTimedSerializer(self.app_secret, salt='session-token')
            return s.dumps(username, salt='session-token')
        except Exception:
            return None

    def verify_session_token(self, token: str) -> str:
        """Valida o token de sessão do usuário."""
        try:
            s = URLSafeTimedSerializer(self.app_secret, salt='session-token')
            return s.loads(token, salt='session-token', max_age=900)
        except (SignatureExpired, BadSignature):
            return None
