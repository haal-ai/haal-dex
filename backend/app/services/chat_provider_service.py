from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass

from app.config import Settings, get_settings
from app.engine.bedrock_runtime_proxy import resolve_aws_profile
from app.engine.model_factory import ModelFactory
from app.models.pipeline import ProviderConfig
from app.services.copilot_auth import CopilotAuth


@dataclass
class ChatProviderStatus:
    provider_type: str
    model_id: str
    signed_in: bool
    requires_sign_in: bool
    display_name: str
    region: str | None = None
    profile: str | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ChatProviderService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @staticmethod
    def _build_aws_cli_command(*args: str, profile: str | None = None) -> list[str]:
        aws_cli = shutil.which('aws')
        if not aws_cli:
            raise RuntimeError('AWS CLI is not installed or not available on PATH.')
        cmd = [aws_cli, *args]
        if profile:
            cmd.extend(['--profile', profile])
        return cmd

    @staticmethod
    def _command_output(proc: subprocess.CompletedProcess[str]) -> str:
        return (((proc.stdout or '') + '\n' + (proc.stderr or '')).strip())

    @staticmethod
    def _is_expired_sso_token_message(message: str) -> bool:
        normalized = message.lower()
        return 'error when retrieving token from sso' in normalized and 'token has expired' in normalized

    def _run_aws_cli(self, *args: str, profile: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        cmd = self._build_aws_cli_command(*args, profile=profile)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def get_provider_config(self) -> ProviderConfig:
        provider_type = self._settings.chat_provider_type
        if provider_type == 'bedrock':
            region = self._settings.chat_aws_region or ModelFactory._infer_aws_region_from_config()
            return ProviderConfig(
                provider_type='bedrock',
                model_id=self._settings.chat_model_id,
                inference_profile_id=self._settings.chat_bedrock_inference_profile_id or None,
                region=region,
                profile=resolve_aws_profile(self._settings.chat_aws_profile or None),
            )
        if provider_type == 'github_copilot':
            return ProviderConfig(
                provider_type='github_copilot',
                model_id=self._settings.chat_model_id,
            )
        if provider_type == 'openai_compatible':
            return ProviderConfig(
                provider_type='openai_compatible',
                model_id=self._settings.chat_model_id,
                endpoint=self._settings.chat_openai_endpoint or None,
                api_key=self._settings.chat_openai_api_key or None,
            )
        raise ValueError(f'Unsupported chat provider type: {provider_type}')

    def get_status(self) -> ChatProviderStatus:
        config = self.get_provider_config()
        if config.provider_type == 'bedrock':
            return self._get_bedrock_status(config)
        if config.provider_type == 'github_copilot':
            authenticated = CopilotAuth().is_authenticated()
            return ChatProviderStatus(
                provider_type='github_copilot',
                model_id=config.model_id,
                signed_in=authenticated,
                requires_sign_in=not authenticated,
                display_name='GitHub Copilot',
                message=None if authenticated else 'GitHub Copilot sign-in is required before chatting.',
            )
        if config.provider_type == 'openai_compatible':
            configured = bool(config.api_key)
            return ChatProviderStatus(
                provider_type='openai_compatible',
                model_id=config.model_id,
                signed_in=configured,
                requires_sign_in=not configured,
                display_name='OpenAI Compatible',
                message=None if configured else 'Set an API key before chatting with the OpenAI-compatible provider.',
            )
        raise ValueError(f'Unsupported chat provider type: {config.provider_type}')

    def sign_in(self) -> ChatProviderStatus:
        config = self.get_provider_config()
        if config.provider_type == 'bedrock':
            self._sign_in_bedrock(config)
            return self._get_bedrock_status(config, attempt_auto_refresh=False)
        if config.provider_type == 'github_copilot':
            CopilotAuth().get_token()
            return self.get_status()
        if config.provider_type == 'openai_compatible':
            return self.get_status()
        raise ValueError(f'Unsupported chat provider type: {config.provider_type}')

    def _get_bedrock_status(self, config: ProviderConfig, *, attempt_auto_refresh: bool = True) -> ChatProviderStatus:
        profile = config.profile or resolve_aws_profile(None)
        region = config.region or self._settings.chat_aws_region or ModelFactory._infer_aws_region_from_config()
        if not shutil.which('aws'):
            return ChatProviderStatus(
                provider_type='bedrock',
                model_id=config.model_id,
                signed_in=False,
                requires_sign_in=True,
                display_name='AWS Bedrock',
                region=region,
                profile=profile,
                message='AWS CLI is required to check or refresh Bedrock SSO credentials.',
            )

        proc = self._run_aws_cli('sts', 'get-caller-identity', profile=profile, timeout=30)
        message = self._command_output(proc)

        if proc.returncode != 0 and attempt_auto_refresh and profile and self._is_expired_sso_token_message(message):
            try:
                self._sign_in_bedrock(config)
            except RuntimeError as exc:
                message = str(exc) or message
            else:
                proc = self._run_aws_cli('sts', 'get-caller-identity', profile=profile, timeout=30)
                message = self._command_output(proc)

        signed_in = proc.returncode == 0
        message = None if signed_in else (message or 'AWS Bedrock sign-in is required before chatting.')
        return ChatProviderStatus(
            provider_type='bedrock',
            model_id=config.model_id,
            signed_in=signed_in,
            requires_sign_in=not signed_in,
            display_name='AWS Bedrock',
            region=region,
            profile=profile,
            message=message,
        )

    def _sign_in_bedrock(self, config: ProviderConfig) -> None:
        profile = config.profile or resolve_aws_profile(None)
        if not profile:
            raise RuntimeError('No AWS profile is configured for Bedrock sign-in.')
        proc = self._run_aws_cli('sso', 'login', profile=profile, timeout=240)
        if proc.returncode != 0:
            output = self._command_output(proc)
            raise RuntimeError(output or f'aws sso login failed for profile {profile}')
