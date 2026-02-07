"""Shared context-manager mixins for lifecycle-managed components."""

from __future__ import annotations

from typing import TypeVar

_T = TypeVar("_T")


class CloseOnExitMixin:
    """Provide ``with`` support for objects that implement ``close()``."""

    def close(self) -> None:
        """Release resources held by this object."""
        raise NotImplementedError

    def __enter__(self: _T) -> _T:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class StartCloseOnExitMixin(CloseOnExitMixin):
    """Like CloseOnExitMixin, but starts on context entry."""

    def __enter__(self: _T) -> _T:
        # Subclasses are expected to implement start().
        self.start()  # type: ignore[attr-defined]
        return self
