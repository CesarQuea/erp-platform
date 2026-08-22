from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy.orm import Session


class PlatformSessionScopeError(RuntimeError):
    pass


_active_platform_session: ContextVar[Session | None] = ContextVar("active_platform_identity_session", default=None)


class PlatformSessionScope:
    @contextmanager
    def activate(self, session: Session) -> Iterator[None]:
        if _active_platform_session.get() is not None:
            raise PlatformSessionScopeError("Nested platform transaction scopes are not supported")
        token = _active_platform_session.set(session)
        try:
            yield
        finally:
            _active_platform_session.reset(token)

    def current(self) -> Session:
        session = _active_platform_session.get()
        if session is None:
            raise PlatformSessionScopeError("No active platform transaction scope")
        return session
