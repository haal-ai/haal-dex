"""GitHubCopilotModel: custom Strands model provider for GitHub Copilot via OAuth.

Extends strands.models.Model when available, otherwise uses a plain base class.
Implements stream(), structured_output(), update_config(), and get_config()
with OAuth token acquisition.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator, AsyncIterable, Optional, Type, TypeVar, Union
from urllib import request as urllib_request
from urllib.error import URLError
from urllib.parse import urlencode

from app.models.pipeline import OAuthConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Try importing the Strands SDK base Model and types; fall back to plain class.
try:
    from strands.models import Model as _BaseModel
    from strands.types.content import Message
    from strands.types.streaming import StreamEvent
    from strands.types.tools import ToolSpec

    _STRANDS_AVAILABLE = True
except ImportError:

    class _BaseModel:  # type: ignore[no-redef]
        """Fallback base when strands-agents is not installed."""

        pass

    _STRANDS_AVAILABLE = False

# Type aliases for when strands is not available.
if TYPE_CHECKING:
    from strands.types.content import Message
    from strands.types.streaming import StreamEvent
    from strands.types.tools import ToolSpec


class GitHubCopilotModel(_BaseModel):
    """Strands-compatible model provider for GitHub Copilot via OAuth.

    Acquires an OAuth token from the configured token_url using
    client_id / client_secret, then streams completions from the
    GitHub Copilot chat completions API.
    """

    # Default Copilot API endpoint for chat completions.
    COPILOT_API_URL = "https://api.githubcopilot.com/chat/completions"

    def __init__(self, oauth_config: OAuthConfig | None, model_id: str) -> None:
        self.oauth_config = oauth_config
        self.model_id = model_id
        self._token: str | None = None
        self._config: dict[str, Any] = {
            "model_id": model_id,
            "temperature": 0.7,
            "max_tokens": 2048,
        }

    # ------------------------------------------------------------------
    # OAuth token management
    # ------------------------------------------------------------------

    def _acquire_token(self) -> str:
        """Acquire an OAuth token from the configured token_url.

        Uses client_credentials grant with client_id and client_secret.

        Returns:
            The access token string.

        Raises:
            RuntimeError: If oauth_config is missing or the token request fails.
        """
        if self.oauth_config is None:
            raise RuntimeError("Cannot acquire token: oauth_config is not set")

        data = urlencode({
            "client_id": self.oauth_config.client_id,
            "client_secret": self.oauth_config.client_secret,
            "grant_type": "client_credentials",
            "scope": " ".join(self.oauth_config.scopes),
        }).encode("utf-8")

        req = urllib_request.Request(
            self.oauth_config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urllib_request.urlopen(req) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                token = body.get("access_token")
                if not token:
                    raise RuntimeError(f"Token response missing 'access_token': {body}")
                return token
        except URLError as exc:
            raise RuntimeError(f"Failed to acquire OAuth token from {self.oauth_config.token_url}: {exc}") from exc

    def _ensure_token(self) -> str:
        """Return the cached token, acquiring a new one if necessary."""
        if self._token is None:
            self._token = self._acquire_token()
        return self._token

    def invalidate_token(self) -> None:
        """Clear the cached token so the next call re-acquires it."""
        self._token = None

    # ------------------------------------------------------------------
    # Strands Model interface
    # ------------------------------------------------------------------

    def stream(
        self,
        messages: list[Any],
        tool_specs: Optional[list[Any]] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stream a completion from the GitHub Copilot API.

        Sends the request messages to the Copilot chat completions endpoint
        and yields response chunks.

        Args:
            messages: List of message objects to be processed.
            tool_specs: Optional tool specifications (not used by Copilot).
            system_prompt: Optional system prompt.
            tool_choice: Optional tool choice strategy (not used by Copilot).
            **kwargs: Additional keyword arguments.

        Yields:
            Parsed JSON chunks from the Copilot streaming response.

        Raises:
            RuntimeError: On network or authentication errors.
        """
        token = self._ensure_token()

        # Convert strands Message objects to plain dicts if needed.
        formatted_messages: list[dict[str, Any]] = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if isinstance(msg, dict):
                formatted_messages.append(msg)
            else:
                # Strands Message objects — extract role and content.
                formatted_messages.append({
                    "role": getattr(msg, "role", "user"),
                    "content": str(getattr(msg, "content", msg)),
                })

        payload = json.dumps({
            "model": self.model_id,
            "messages": formatted_messages,
            "temperature": self._config.get("temperature", 0.7),
            "max_tokens": self._config.get("max_tokens", 2048),
            "stream": True,
        }).encode("utf-8")

        req = urllib_request.Request(
            self.COPILOT_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib_request.urlopen(req) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if not decoded or not decoded.startswith("data:"):
                        continue
                    data_str = decoded[len("data:"):].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.warning("Skipping unparseable SSE chunk: %s", data_str)
        except URLError as exc:
            # Invalidate token in case it expired, then raise.
            self.invalidate_token()
            raise RuntimeError(
                f"GitHub Copilot API request failed: {exc}"
            ) from exc

    def structured_output(
        self,
        output_model: Type[T],
        prompt: list[Any],
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Get structured output from the model.

        Delegates to stream() and attempts to parse the final response
        into the requested output_model.

        Args:
            output_model: The output model type to parse the response into.
            prompt: The prompt messages.
            system_prompt: Optional system prompt.
            **kwargs: Additional keyword arguments.

        Yields:
            Model events with the last being the structured output.
        """
        # Collect the full streamed response.
        full_content = ""
        for chunk in self.stream(prompt, system_prompt=system_prompt, **kwargs):
            if isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    full_content += content
                    yield {"chunk": content}

        # Attempt to parse the accumulated content into the output model.
        try:
            parsed = json.loads(full_content)
            result = output_model(**parsed) if isinstance(parsed, dict) else output_model(parsed)
        except Exception:
            result = full_content  # type: ignore[assignment]

        yield {"output": result}

    def update_config(self, **kwargs: Any) -> None:
        """Update model configuration parameters.

        Supported keys: model_id, temperature, max_tokens.

        Args:
            **kwargs: Configuration key-value pairs to update.
        """
        for key, value in kwargs.items():
            if key == "model_id":
                self.model_id = value
            self._config[key] = value

    def get_config(self) -> dict[str, Any]:
        """Return the current model configuration."""
        return dict(self._config)
