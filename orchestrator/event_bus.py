"""In-process event bus for orchestrator events."""

import logging
import time
from datetime import datetime
from typing import Callable

logger = logging.getLogger("onjaro.events")


class EventBus:
    """Simple pub/sub event bus for run lifecycle events."""

    def __init__(self):
        self._subscribers: list[Callable] = []

    def subscribe(self, callback: Callable) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        self._subscribers = [s for s in self._subscribers if s != callback]

    def emit(self, run_id: str, phase: str, agent_name: str, severity: str,
             event_type: str, message: str, data: dict = None) -> dict:
        event = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "agent_name": agent_name,
            "severity": severity,
            "event_type": event_type,
            "message": message,
            "data": data or {},
        }

        # Log to Python logger
        log_level = {
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "DECISION": logging.INFO,
        }.get(severity, logging.INFO)

        logger.log(log_level, "[%s] [%s] [%s] %s", run_id[:8], phase, agent_name, message)

        # Notify all subscribers
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error("Event subscriber error: %s", e)

        return event
