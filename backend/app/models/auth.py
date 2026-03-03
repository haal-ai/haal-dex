from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserContext:
    user_id: str
    username: str
    roles: list[str]  # e.g. ["admin", "user"]
    token: str


@dataclass
class AuthToken:
    access_token: str
    token_type: str
    expires_in: int
    user_id: str
    roles: list[str]


@dataclass
class LoginRequest:
    username: str
    password: str
