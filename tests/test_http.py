from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from scripts.sources import http


def test_pool_is_reused_within_thread_and_not_shared_with_workers():
    main_session = http.session()
    assert http.session() is main_session
    with ThreadPoolExecutor(max_workers=1) as executor:
        other = executor.submit(http.session).result()
        assert other is executor.submit(http.session).result()
    assert other is not main_session


def test_retry_policy_is_bounded_and_does_not_retry_forbidden():
    policy = http.session().get_adapter("https://").max_retries
    assert policy.total == 2
    assert policy.is_retry("GET", 503)
    assert policy.is_retry("GET", 429)
    assert not policy.is_retry("GET", 403)
    assert not policy.is_retry("POST", 503)
    assert not policy.respect_retry_after_header


def test_shared_client_supplies_default_timeout():
    with patch.object(http.session(), "get") as get:
        http.get("https://example.com")
        get.assert_called_once_with("https://example.com", timeout=(10, 20))
