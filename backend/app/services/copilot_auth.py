from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

GITHUB_CLIENT_ID = 'Iv1.b507a08c87ecfe98'
DEVICE_CODE_URL = 'https://github.com/login/device/code'
ACCESS_TOKEN_URL = 'https://github.com/login/oauth/access_token'
COPILOT_TOKEN_URL = 'https://api.github.com/copilot_internal/v2/token'
DEFAULT_TOKEN_DIR = Path.home() / '.config' / 'intent' / 'copilot'


def _ssl_context_arg() -> dict[str, Any]:
    return {}


class CopilotAuth:
    def __init__(self, token_dir: Path | None = None) -> None:
        self._token_dir = token_dir or DEFAULT_TOKEN_DIR
        self._token_dir.mkdir(parents=True, exist_ok=True)
        self._github_token_file = self._token_dir / 'github_token.json'
        self._copilot_token: str | None = None
        self._copilot_token_expires: float = 0

    def get_token(self) -> str:
        github_token = self._load_github_token()
        if not github_token:
            github_token = self._device_flow()
            self._save_github_token(github_token)

        if not self._copilot_token or time.time() >= self._copilot_token_expires:
            self._refresh_copilot_token(github_token)

        if not self._copilot_token:
            raise RuntimeError('Unable to acquire GitHub Copilot token')
        return self._copilot_token

    @staticmethod
    def copilot_headers() -> dict[str, str]:
        return {
            'editor-version': 'vscode/1.85.1',
            'editor-plugin-version': 'copilot/1.155.0',
            'Copilot-Integration-Id': 'vscode-chat',
            'user-agent': 'GithubCopilot/1.155.0',
        }

    def is_authenticated(self) -> bool:
        return self._load_github_token() is not None

    def logout(self) -> None:
        if self._github_token_file.exists():
            self._github_token_file.unlink()
        self._copilot_token = None
        self._copilot_token_expires = 0

    def _post_form(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        data = urllib_parse.urlencode(form).encode('utf-8')
        req = urllib_request.Request(
            url,
            data=data,
            headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with urllib_request.urlopen(req, **_ssl_context_arg()) as response:
            return json.loads(response.read().decode('utf-8'))

    def _get_json(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        req = urllib_request.Request(url, headers=headers, method='GET')
        try:
            with urllib_request.urlopen(req, **_ssl_context_arg()) as response:
                status = getattr(response, 'status', 200)
                return status, json.loads(response.read().decode('utf-8'))
        except urllib_error.HTTPError as exc:
            body = exc.read().decode('utf-8') if exc.fp is not None else '{}'
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {'raw': body}
            return exc.code, parsed

    def _device_flow(self) -> str:
        print('\nGitHub Copilot authentication is required.', file=sys.stderr)
        data = self._post_form(
            DEVICE_CODE_URL,
            {'client_id': GITHUB_CLIENT_ID, 'scope': 'copilot'},
        )

        device_code = str(data['device_code'])
        user_code = str(data['user_code'])
        verification_uri = str(data.get('verification_uri', 'https://github.com/login/device'))
        interval = int(data.get('interval', 5))
        expires_in = int(data.get('expires_in', 900))

        print(f'Open: {verification_uri}', file=sys.stderr)
        print(f'Enter code: {user_code}', file=sys.stderr)
        print(f'Waiting for authorization (expires in {expires_in}s)...', file=sys.stderr)

        deadline = time.time() + expires_in
        while time.time() < deadline:
            time.sleep(interval)
            token_data = self._post_form(
                ACCESS_TOKEN_URL,
                {
                    'client_id': GITHUB_CLIENT_ID,
                    'device_code': device_code,
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                },
            )

            if 'access_token' in token_data:
                print('GitHub Copilot authenticated successfully.', file=sys.stderr)
                return str(token_data['access_token'])

            error = str(token_data.get('error', ''))
            if error == 'authorization_pending':
                continue
            if error == 'slow_down':
                interval += 5
                continue
            if error == 'expired_token':
                raise RuntimeError('GitHub device code expired. Please try again.')
            if error == 'access_denied':
                raise RuntimeError('GitHub authorization denied.')
            raise RuntimeError(f"GitHub OAuth error: {error} - {token_data.get('error_description', '')}")

        raise RuntimeError('GitHub device flow timed out. Please try again.')

    def _refresh_copilot_token(self, github_token: str) -> None:
        status, data = self._get_json(
            COPILOT_TOKEN_URL,
            {
                'Authorization': f'token {github_token}',
                'Accept': 'application/json',
                'editor-version': 'vscode/1.85.1',
                'editor-plugin-version': 'copilot-chat/0.22.4',
                'user-agent': 'GithubCopilot/1.155.0',
            },
        )

        if status == 401:
            self.logout()
            raise RuntimeError('GitHub token was rejected. Run authentication again.')

        if status == 403:
            self._copilot_token = github_token
            self._copilot_token_expires = time.time() + 3600
            return

        if status >= 400:
            raise RuntimeError(f'GitHub Copilot token exchange failed: {data}')

        self._copilot_token = str(data['token'])
        self._copilot_token_expires = float(data.get('expires_at', time.time() + 1800)) - 60

    def _load_github_token(self) -> str | None:
        if not self._github_token_file.exists():
            return None
        try:
            data = json.loads(self._github_token_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return None
        token = data.get('access_token')
        return str(token) if token else None

    def _save_github_token(self, token: str) -> None:
        self._github_token_file.write_text(
            json.dumps({'access_token': token}, indent=2),
            encoding='utf-8',
        )
