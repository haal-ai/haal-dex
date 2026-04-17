from __future__ import annotations

import subprocess

from app.config import Settings
from app.services.chat_provider_service import ChatProviderService


def _completed_process(*, returncode: int, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=['aws'], returncode=returncode, stdout=stdout, stderr=stderr)


def _bedrock_settings() -> Settings:
    return Settings(
        chat_provider_type='bedrock',
        chat_model_id='anthropic.claude-3-haiku-20240307-v1:0',
        chat_aws_profile='claude-sso',
        chat_aws_region='us-east-1',
    )


class TestChatProviderServiceBedrockStatus:
    def test_auto_refreshes_expired_sso_token_before_reporting_signed_out(self, monkeypatch):
        service = ChatProviderService(_bedrock_settings())
        calls: list[tuple[tuple[str, ...], str | None, int]] = []
        responses = iter([
            _completed_process(
                returncode=1,
                stderr='Error when retrieving token from sso: Token has expired and refresh failed',
            ),
            _completed_process(returncode=0, stdout='Successfully logged into Start URL: https://example.awsapps.com/start'),
            _completed_process(returncode=0, stdout='{"Account":"123456789012"}'),
        ])

        monkeypatch.setattr('app.services.chat_provider_service.shutil.which', lambda command: 'aws' if command == 'aws' else None)

        def fake_run_aws_cli(self, *args: str, profile: str | None = None, timeout: int = 30):
            calls.append((args, profile, timeout))
            return next(responses)

        monkeypatch.setattr(ChatProviderService, '_run_aws_cli', fake_run_aws_cli)

        status = service.get_status()

        assert status.signed_in is True
        assert status.requires_sign_in is False
        assert status.message is None
        assert calls == [
            (('sts', 'get-caller-identity'), 'claude-sso', 30),
            (('sso', 'login'), 'claude-sso', 240),
            (('sts', 'get-caller-identity'), 'claude-sso', 30),
        ]

    def test_does_not_auto_refresh_for_non_expired_token_failure(self, monkeypatch):
        service = ChatProviderService(_bedrock_settings())
        calls: list[tuple[tuple[str, ...], str | None, int]] = []

        monkeypatch.setattr('app.services.chat_provider_service.shutil.which', lambda command: 'aws' if command == 'aws' else None)

        def fake_run_aws_cli(self, *args: str, profile: str | None = None, timeout: int = 30):
            calls.append((args, profile, timeout))
            return _completed_process(returncode=1, stderr='Unable to locate credentials')

        monkeypatch.setattr(ChatProviderService, '_run_aws_cli', fake_run_aws_cli)

        status = service.get_status()

        assert status.signed_in is False
        assert status.requires_sign_in is True
        assert status.message == 'Unable to locate credentials'
        assert calls == [
            (('sts', 'get-caller-identity'), 'claude-sso', 30),
        ]

    def test_sign_in_checks_status_without_triggering_a_second_refresh(self, monkeypatch):
        service = ChatProviderService(_bedrock_settings())
        calls: list[tuple[tuple[str, ...], str | None, int]] = []
        responses = iter([
            _completed_process(returncode=0, stdout='Successfully logged into Start URL: https://example.awsapps.com/start'),
            _completed_process(returncode=1, stderr='Error when retrieving token from sso: Token has expired and refresh failed'),
        ])

        monkeypatch.setattr('app.services.chat_provider_service.shutil.which', lambda command: 'aws' if command == 'aws' else None)

        def fake_run_aws_cli(self, *args: str, profile: str | None = None, timeout: int = 30):
            calls.append((args, profile, timeout))
            return next(responses)

        monkeypatch.setattr(ChatProviderService, '_run_aws_cli', fake_run_aws_cli)

        status = service.sign_in()

        assert status.signed_in is False
        assert status.requires_sign_in is True
        assert status.message == 'Error when retrieving token from sso: Token has expired and refresh failed'
        assert calls == [
            (('sso', 'login'), 'claude-sso', 240),
            (('sts', 'get-caller-identity'), 'claude-sso', 30),
        ]
