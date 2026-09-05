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

    Checks PULSEFLOW_BASE_URL first, then TECHPULSE_TARGET, falling back to
    http://127.0.0.1:8000.
    We normalise by stripping a trailing /events suffix so that client code
    can append paths cleanly via urljoin / string concatenation.
    """
    raw = os.environ.get("PULSEFLOW_BASE_URL") or os.environ.get("TECHPULSE_TARGET", "http://127.0.0.1:8000")
    # Strip accidental /events suffix – the client owns path construction.
    return raw.rstrip("/").removesuffix("/events")


# ---------------------------------------------------------------------------
# Resolved constants (import these from other modules)
# ---------------------------------------------------------------------------

#: Base URL of the PulseFlow pipeline ingestion server (Machine Two).
PIPELINE_BASE_URL: str = _get_base_url()

#: Host for the TechPulse Control API server (Machine One).
TECHPULSE_HOST: str = os.environ.get("TECHPULSE_HOST", "0.0.0.0")

#: Port for the TechPulse Control API server (Machine One).
TECHPULSE_PORT: int = int(os.environ.get("TECHPULSE_PORT", "8001"))

#: Default HTTP request timeout for a single batch send (seconds).
DEFAULT_HTTP_TIMEOUT: float = 10.0

#: The traffic profile to run (dynamic, steady, ramp, surge, harmonic)
TECHPULSE_PROFILE: str = os.environ.get("TECHPULSE_PROFILE", "dynamic").lower()

#: Baseline event rate (events/sec)
DEFAULT_BASELINE_RATE: float = float(os.environ.get("BASELINE_RATE", os.environ.get("TECHPULSE_RATE", "100.0")))
TECHPULSE_RATE: float = DEFAULT_BASELINE_RATE

#: Maximum safety limit for custom spikes (events/sec)
MAX_CUSTOM_RATE: int = int(os.environ.get("MAX_CUSTOM_RATE", "50000"))

#: Number of events to send per HTTP batch
TECHPULSE_BATCH_SIZE: int = int(os.environ.get("TECHPULSE_BATCH_SIZE", "50"))

#: Number of concurrent async producer tasks.
#: The configured target rate is the TOTAL aggregate rate across all tasks.
TECHPULSE_CONCURRENCY: int = max(1, int(os.environ.get("TECHPULSE_CONCURRENCY", "4")))

#: Configurable default weighted event distribution
DEFAULT_EVENT_DISTRIBUTION: dict[str, float] = {
    "CLICK": 30.0,
    "PAGE_VIEW": 25.0,
    "LOG": 15.0,
    "CART_ADD": 10.0,
    "INVENTORY_UPDATE": 10.0,
    "ORDER": 5.0,
    "PAYMENT": 5.0,
}

