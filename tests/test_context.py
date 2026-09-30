from homeassistant.core import Context

from custom_components.entity_controller.context import ContextTracker


def test_action_context_links_parent_and_is_recognized() -> None:
    tracker = ContextTracker(max_contexts=8)
    parent = Context(user_id="user-1")

    context = tracker.new_action_context(parent)

    assert context.parent_id == parent.id
    assert tracker.is_own_context(context)


def test_child_context_of_controller_action_is_recognized() -> None:
    tracker = ContextTracker(max_contexts=8)
    action_context = tracker.new_action_context(None)
    child = Context(parent_id=action_context.id)

    assert tracker.is_own_context(child)


def test_context_tracker_evicts_old_contexts() -> None:
    tracker = ContextTracker(max_contexts=2)
    first = tracker.new_action_context(None)
    tracker.new_action_context(None)
    tracker.new_action_context(None)

    assert not tracker.is_own_context(first)
