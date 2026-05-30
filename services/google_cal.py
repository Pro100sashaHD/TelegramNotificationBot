import os
import json
import secrets
import hashlib
import base64
from google_auth_oauthlib.flow import Flow

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = 'credentials.json'
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'

_saved_code_verifier = None


def get_authorization_url(user_id: int) -> str:
    """Генерирует ссылку для авторизации с явным ручным контролем PKCE."""
    global _saved_code_verifier

    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(f"Файл {CREDENTIALS_FILE} не найден!")

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    _saved_code_verifier = secrets.token_urlsafe(64)

    hashed = hashlib.sha256(_saved_code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode('utf-8').replace('=', '')

    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        code_challenge=code_challenge,
        code_challenge_method='S256'
    )

    return auth_url


def build_credentials_from_code(code: str):
    """Обменивает код на токены, используя сохраненный на первом шаге verifier."""
    global _saved_code_verifier

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    if not _saved_code_verifier:
        _saved_code_verifier = secrets.token_urlsafe(64)

    flow.code_verifier = _saved_code_verifier

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials

        return json.dumps({
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        })
    except Exception as e:
        raise e