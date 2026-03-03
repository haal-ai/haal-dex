# Feature: intent, Property 28: Unauthenticated request rejection
"""Property 28: Unauthenticated request rejection

For any unauthenticated request to a protected endpoint, the system should
reject with 401.

**Validates: Requirements 20.1, 20.2, 20.3**

Strategy: Generate random Authorization header values — missing, empty,
random garbage strings, and malformed Bearer tokens — then verify that
every protected endpoint returns HTTP 401.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Random printable strings (garbage tokens, partial JWTs, etc.)
_garbage_text = st.text(
    alphabet=string.printable, min_size=0, max_size=200
)

# Various malformed Authorization header values
_bad_auth_headers = st.one_of(
    # Completely missing header → represented as None
    st.none(),
    # Empty string
    st.just(""),
    # Random garbage (no "Bearer " prefix)
    _garbage_text,
    # "Bearer " followed by garbage (not a valid JWT)
    _garbage_text.map(lambda t: f"Bearer {t}"),
    # Wrong scheme
    _garbage_text.map(lambda t: f"Basic {t}"),
    _garbage_text.map(lambda t: f"Token {t}"),
)

# Protected endpoints to test (method, path)
PROTECTED_ENDPOINTS = [
    ("GET", "/api/auth/me"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(auth_header=_bad_auth_headers)
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected_with_401(auth_header):
    """Property 28: Any unauthenticated request to a protected endpoint
    should be rejected with HTTP 401.

    We generate random Authorization header values (missing, empty, garbage,
    malformed Bearer tokens) and verify every protected endpoint returns 401.
    """
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for method, path in PROTECTED_ENDPOINTS:
            headers = {}
            if auth_header is not None:
                headers["Authorization"] = auth_header

            response = await client.request(method, path, headers=headers)

            assert response.status_code == 401, (
                f"Expected 401 for {method} {path} with "
                f"Authorization={auth_header!r}, got {response.status_code}"
            )
