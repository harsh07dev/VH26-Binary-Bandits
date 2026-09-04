"""PulseFlow module: config.

TechPulse runtime configuration.

Values are read from environment variables so that the same code works in local
two-process development and future Docker/CI environments.

Environment variables (see .env.example):
    TECHPULSE_TARGET   – full URL prefix for the PulseFlow pipeline, e.g.
                          http://127.0.0.1:8000
                          NOTE: .env.example stores the full /events URL; we
                          strip any trailing /events so the client can append
                          the path itself cleanly.
    PULSEFLOW_HOST     – host the pipeline server listens on (Machine Two)
    PULSEFLOW_PORT     – port the pipeline server listens on (Machine Two)
"""

import os


def _get_base_url() -> str:
    """Resolve the base URL for the PulseFlow pipeline from the environment.

    .env.example ships TECHPULSE_TARGET=http://127.0.0.1:8000/events
    We normalise by stripping a trailing /events suffix so that client code
    can append paths cleanly via urljoin / string concatenation.
    """
    raw = os.environ.get("TECHPULSE_TARGET", "http://127.0.0.1:8000")
    # Strip accidental /events suffix – the client owns path construction.
    return raw.rstrip("/").removesuffix("/events")


# ---------------------------------------------------------------------------
# Resolved constants (import these from other modules)
# ---------------------------------------------------------------------------

#: Base URL of the PulseFlow pipeline ingestion server.
PIPELINE_BASE_URL: str = _get_base_url()

#: Default HTTP request timeout for a single batch send (seconds).
DEFAULT_HTTP_TIMEOUT: float = 10.0

#: The traffic profile to run (steady, ramp, surge, harmonic)
TECHPULSE_PROFILE: str = os.environ.get("TECHPULSE_PROFILE", "steady").lower()

#: Baseline event rate (events/sec)
TECHPULSE_RATE: float = float(os.environ.get("TECHPULSE_RATE", "100.0"))

#: Number of events to send per HTTP batch
TECHPULSE_BATCH_SIZE: int = int(os.environ.get("TECHPULSE_BATCH_SIZE", "50"))
