# app/utils/logger.py
import logging
import json
import os

logger = logging.getLogger("genai_app")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    # Simple formatter because the content itself is JSON
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

def log_event(event: str, trace_id: str = "internal", **kwargs):
    """
    Production-grade structured logging. 
    Every log must have a trace_id to correlate events.
    """
    payload = {
        "event": event,
        "trace_id": trace_id,
        "env": os.getenv("APP_ENV", "dev"),
        **kwargs,
    }
    logger.info(json.dumps(payload))