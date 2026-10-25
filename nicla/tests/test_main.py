"""Tests for the hardware-free logic in nicla/main.py (run under CPython)."""
from main import (BROADCAST, COOLDOWN, DEBOUNCE_HITS, MONITOR,
                  PERSON_THRESHOLD, Debouncer, Watchman)

PERSON, EMPTY = 0.95, 0.1
STEP_MS = 200


def feed(watchman, scores, start_ms=0, step_ms=STEP_MS):
    """Feed scores one frame at a time; return the transitions seen."""
    seen = []
    for i, score in enumerate(scores):
        changed = watchman.update(start_ms + i * step_ms, score)
        if changed:
            seen.append(changed)
    return seen


def confirm(watchman):
    """Drive a fresh Watchman into BROADCAST; return the time it happened."""
    assert feed(watchman, [PERSON] * DEBOUNCE_HITS) == [BROADCAST]
    return (DEBOUNCE_HITS - 1) * STEP_MS


def test_debouncer_needs_three_of_last_five():
    d = Debouncer(window=5, hits=3)
    assert [d.update(x) for x in (1, 0, 1, 0)] == [False] * 4
    assert d.update(1) is True


def test_debouncer_forgets_frames_outside_window():
    d = Debouncer(window=5, hits=3)
    for x in (1, 1, 0, 0, 0, 0):
        d.update(x)
    assert d.update(1) is False  # only one hit left in the window


def test_default_needs_four_of_five():
    w = Watchman(0)
    assert feed(w, [PERSON, PERSON, EMPTY, PERSON]) == []
    assert w.update(800, PERSON) == BROADCAST


def test_isolated_person_frames_do_not_trigger():
    w = Watchman(0)
    assert feed(w, [PERSON, EMPTY, EMPTY, PERSON, EMPTY, EMPTY, PERSON, EMPTY]) == []
    assert w.state == MONITOR


def test_scores_below_default_threshold_do_not_trigger():
    w = Watchman(0)
    assert feed(w, [PERSON_THRESHOLD - 0.01] * 10) == []


def test_score_on_threshold_counts_as_person():
    w = Watchman(0, threshold=0.7, debouncer=Debouncer(window=5, hits=3))
    assert feed(w, [0.7, 0.7, 0.7]) == [BROADCAST]


def test_confirmed_person_enters_broadcast():
    w = Watchman(0)
    confirm(w)
    assert w.reason == "person confirmed"


def test_full_cycle_by_timeout():
    w = Watchman(0, broadcast_timeout_ms=12000, cooldown_ms=30000)
    t = confirm(w)
    assert w.update(t + 11999) is None
    assert w.update(t + 12000) == COOLDOWN
    assert w.reason == "broadcast timeout"
    assert w.update(t + 12000 + 29999) is None
    assert w.update(t + 12000 + 30000) == MONITOR


def test_stop_from_pi_ends_broadcast_early():
    w = Watchman(0)
    t = confirm(w)
    assert w.stop(t + 600) == COOLDOWN
    assert w.reason == "stop from Pi"


def test_stop_outside_broadcast_is_ignored():
    w = Watchman(0)
    assert w.stop(100) is None
    assert w.state == MONITOR


def test_scores_ignored_during_cooldown():
    w = Watchman(0, broadcast_timeout_ms=1000, cooldown_ms=5000)
    t = confirm(w)
    w.update(t + 1000)                       # -> COOLDOWN
    assert feed(w, [PERSON] * 10, start_ms=t + 1200) == []
    assert w.state == COOLDOWN


def test_debounce_history_cleared_after_cooldown():
    w = Watchman(0, broadcast_timeout_ms=1000, cooldown_ms=1000)
    t = confirm(w)
    w.update(t + 1000)                       # COOLDOWN
    assert w.update(t + 2000) == MONITOR
    # One frame short of the debounce is not enough on its own after the reset.
    assert feed(w, [PERSON] * (DEBOUNCE_HITS - 1), start_ms=t + 2200) == []
