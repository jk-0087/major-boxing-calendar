"""Thread-local connection pooling and bounded, read-only request retries."""
from threading import local

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "Chrome/126.0 Safari/537.36 MajorBoxingCalendar/1.0"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}
_state = local()


def session() -> requests.Session:
    # Sessions are never shared across discovery worker threads.
    if not hasattr(_state, "session"):
        client = requests.Session()
        retries = Retry(
            total=2, connect=2, read=2, status=2, backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}), raise_on_status=False,
            respect_retry_after_header=False,
        )
        for scheme in ("https://", "http://"):
            client.mount(scheme, HTTPAdapter(max_retries=retries))
        client.headers.update(HEADERS)
        _state.session = client
    return _state.session


def get(url: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", (10, 20))
    return session().get(url, **kwargs)
