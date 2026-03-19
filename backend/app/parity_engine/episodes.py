from __future__ import annotations

from .models import EpisodeStatus


ALLOWED_TRANSITIONS: dict[EpisodeStatus, set[EpisodeStatus]] = {
    EpisodeStatus.QUEUED: {EpisodeStatus.PROCESSING, EpisodeStatus.FAILED},
    EpisodeStatus.PROCESSING: {EpisodeStatus.PROCESSED, EpisodeStatus.FAILED},
    EpisodeStatus.PROCESSED: set(),
    EpisodeStatus.FAILED: set(),
}


def validate_status_transition(current: str, next_status: str) -> None:
    current_state = EpisodeStatus(current)
    next_state = EpisodeStatus(next_status)
    if next_state not in ALLOWED_TRANSITIONS[current_state]:
        raise ValueError(f"Invalid episode transition: {current_state.value} -> {next_state.value}")
