"""Home Assistant Context tracking for Entity Controller actions."""

from __future__ import annotations

from collections import deque

from homeassistant.core import Context


class ContextTracker:
    """Track recent contexts created by any controller in one EC manager."""

    def __init__(self, *, max_contexts: int = 256) -> None:
        if max_contexts < 1:
            raise ValueError("max_contexts must be at least 1")
        self._max_contexts = max_contexts
        self._ids: deque[str] = deque()
        self._id_set: set[str] = set()

    def remember(self, context: Context) -> None:
        """Remember a controller-owned context id with bounded storage."""

        context_id = context.id
        if context_id in self._id_set:
            return
        while len(self._ids) >= self._max_contexts:
            expired = self._ids.popleft()
            self._id_set.discard(expired)
        self._ids.append(context_id)
        self._id_set.add(context_id)

    def new_action_context(self, parent: Context | None) -> Context:
        """Create and remember a context linked to the triggering context."""

        context = Context(parent_id=parent.id if parent is not None else None)
        self.remember(context)
        return context

    def is_own_context(self, context: Context | None) -> bool:
        """Return whether an event belongs to EC or descends from an EC action."""

        if context is None:
            return False
        return context.id in self._id_set or context.parent_id in self._id_set
