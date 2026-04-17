from __future__ import annotations

import configparser
import os
import subprocess
from pathlib import Path
from typing import Any


def _configured_aws_profiles() -> list[str]:
    config_path = Path.home() / '.aws' / 'config'
    if not config_path.exists():
        return []

    parser = configparser.RawConfigParser()
    try:
        parser.read(config_path, encoding='utf-8')
    except Exception:
        return []

    profiles: list[str] = []
    for section in parser.sections():
        if section == 'default':
            profiles.append('default')
        elif section.startswith('profile '):
            profiles.append(section[len('profile '):])
    return profiles


def resolve_aws_profile(preferred: str | None = None) -> str | None:
    if preferred:
        return preferred

    env_profile = os.environ.get('AWS_PROFILE') or os.environ.get('AWS_DEFAULT_PROFILE')
    if env_profile:
        return env_profile

    config_path = Path.home() / '.aws' / 'config'
    if config_path.exists():
        parser = configparser.RawConfigParser()
        try:
            parser.read(config_path, encoding='utf-8')
            for section in parser.sections():
                if section.startswith('profile '):
                    name = section[len('profile '):]
                elif section == 'default':
                    name = 'default'
                else:
                    continue

                keys = {key.lower() for key, _ in parser.items(section)}
                if any(key.startswith('sso_') for key in keys):
                    return name
        except Exception:
            pass

    profiles = _configured_aws_profiles()
    for profile in profiles:
        if profile != 'default':
            return profile
    return 'default' if profiles else None


def is_bedrock_auth_error(error: Exception) -> bool:
    err_name = getattr(error, '__class__', type(error)).__name__.lower()
    err_str = str(error).lower()
    indicators = [
        'expiredtokenexception',
        'unrecognizedclientexception',
        'security token included in the request is invalid',
        'invalid security token',
        'the security token included in the request is invalid',
        'expired token',
        'unauthorized',
        'unable to locate credentials',
        'could not load credentials',
        'sso',
    ]
    return any(indicator in err_name or indicator in err_str for indicator in indicators)


class BedrockRuntimeClientProxy:
    def __init__(
        self,
        client: Any,
        *,
        model_id: str,
        agent_name: str = 'chat',
        aws_profile: str | None = None,
        aws_region: str | None = None,
        token_tracker: Any | None = None,
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._agent_name = agent_name
        self._aws_profile = resolve_aws_profile(aws_profile)
        self._aws_region = aws_region
        self._token_tracker = token_tracker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def _build_session(self):
        import boto3

        kwargs: dict[str, Any] = {}
        if self._aws_profile:
            kwargs['profile_name'] = self._aws_profile
        if self._aws_region:
            kwargs['region_name'] = self._aws_region
        return boto3.Session(**kwargs)

    def _refresh_credentials(self) -> None:
        profile = resolve_aws_profile(self._aws_profile)
        if not profile:
            raise RuntimeError('No AWS profile available for Bedrock sign-in')

        refresh_cmd = ['aws', 'sso', 'login', '--profile', profile]
        proc = subprocess.run(refresh_cmd, capture_output=True, text=True, timeout=240)
        if proc.returncode != 0:
            output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
            raise RuntimeError(output or f'aws sso login failed for profile {profile}')

        session = self._build_session()
        self._client = session.client('bedrock-runtime', region_name=self._aws_region)

    def _call_with_refresh(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._client, method_name)
        try:
            return method(*args, **kwargs)
        except Exception as exc:
            if not is_bedrock_auth_error(exc):
                raise
            self._refresh_credentials()
            method = getattr(self._client, method_name)
            return method(*args, **kwargs)

    def converse(self, *args: Any, **kwargs: Any) -> Any:
        response = self._call_with_refresh('converse', *args, **kwargs)
        if self._token_tracker is not None and hasattr(self._token_tracker, 'track_request'):
            self._token_tracker.track_request(
                response,
                model_id=self._model_id,
                agent_name=self._agent_name,
            )
        return response

    def invoke_model(self, *args: Any, **kwargs: Any) -> Any:
        return self._call_with_refresh('invoke_model', *args, **kwargs)

    def invoke_model_with_response_stream(self, *args: Any, **kwargs: Any) -> Any:
        return self._call_with_refresh('invoke_model_with_response_stream', *args, **kwargs)
