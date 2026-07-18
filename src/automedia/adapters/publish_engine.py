"""PublishEngine — iterate all enabled adapters and publish.

Error classification and retry logic:

* ``rate_limited`` — exponential backoff, max 3 retries
* ``network_error`` — exponential backoff, max 2 retries
* ``credential_expired`` — triggers credential refresh via accounts/auth
  framework (max 1 attempt), then retries publish once.
* ``credential_refresh_failed`` — returned when refresh also fails;
  requires human reconnection.
* ``content_rejected`` / ``unknown`` — never retried.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from structlog import get_logger

from automedia.adapters.base import (
    AUTOMATION_DEFAULTS,
    BasePlatformAdapter,
    PublishResult,
)
from automedia.adapters.registry import AdapterRegistry

log = get_logger(__name__)

# Valid automation levels recognised by the engine.
_AUTO = "auto"
_REVIEW = "review"
_MANUAL = "manual"

# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

CREDENTIAL_EXPIRED = "credential_expired"
"""The platform credentials/tokens have expired.  Triggers a credential
refresh via :meth:`PublishEngine._refresh_credential`; if the refresh
succeeds the publish is retried once."""

CREDENTIAL_REFRESH_FAILED = "credential_refresh_failed"
"""Credential refresh attempt failed.  The action is ``reconnect_account``
— a human must re-authenticate the account on the platform."""

RATE_LIMITED = "rate_limited"
"""API rate limit exceeded.  Auto-retried with exponential backoff
(``2 ** attempt`` seconds), max 3 retries."""

NETWORK_ERROR = "network_error"
"""Transient network failure (timeout, DNS, connection reset).
Auto-retried with exponential backoff, max 2 retries."""

CONTENT_REJECTED = "content_rejected"
"""Published content was rejected by the platform (policy violation,
sensitive content, spam).  Not retryable — requires human review."""

UNKNOWN = "unknown"
"""Unclassified error.  Not retryable — requires investigation."""

# ---------------------------------------------------------------------------
# Error metadata
# ---------------------------------------------------------------------------

#: Mapping ``error_code -> (retryable, max_retries, suggested_action)``.
#:
#: ``max_retries=``\ ``None`` means the error is marked retryable but
#: is *not* auto-retried by the engine.
_ERROR_META: dict[str, tuple[bool, int | None, str]] = {
    CREDENTIAL_EXPIRED: (True, None, "refresh_credential"),
    CREDENTIAL_REFRESH_FAILED: (False, None, "reconnect_account"),
    RATE_LIMITED: (True, 3, "retry"),
    NETWORK_ERROR: (True, 2, "retry"),
    CONTENT_REJECTED: (False, None, "fix_content"),
    UNKNOWN: (False, None, "investigate"),
}

# ---------------------------------------------------------------------------
# Error classification — reason-string patterns
# ---------------------------------------------------------------------------

_REASON_PATTERNS: list[tuple[str, str]] = [
    # credential_expired
    ("token expired", CREDENTIAL_EXPIRED),
    ("invalid credential", CREDENTIAL_EXPIRED),
    ("access_token", CREDENTIAL_EXPIRED),
    ("401", CREDENTIAL_EXPIRED),
    ("403", CREDENTIAL_EXPIRED),
    ("cookie expired", CREDENTIAL_EXPIRED),
    ("invalid cookie", CREDENTIAL_EXPIRED),
    ("unauthorized", CREDENTIAL_EXPIRED),
    ("auth failed", CREDENTIAL_EXPIRED),
    # rate_limited
    ("429", RATE_LIMITED),
    ("rate limit", RATE_LIMITED),
    ("too many requests", RATE_LIMITED),
    # network_error
    ("connection", NETWORK_ERROR),
    ("timeout", NETWORK_ERROR),
    ("unreachable", NETWORK_ERROR),
    ("dns", NETWORK_ERROR),
    ("ConnectionError", NETWORK_ERROR),
    ("ConnectTimeout", NETWORK_ERROR),
    ("RemoteProtocolError", NETWORK_ERROR),
    ("ReadTimeout", NETWORK_ERROR),
    ("WriteTimeout", NETWORK_ERROR),
    ("PoolTimeout", NETWORK_ERROR),
    ("NetworkError", NETWORK_ERROR),
    ("ProtocolError", NETWORK_ERROR),
    # content_rejected
    ("content rejected", CONTENT_REJECTED),
    ("\u654f\u611f\u8bcd", CONTENT_REJECTED),  # 敏感词
    ("\u8fdd\u53cd", CONTENT_REJECTED),  # 违反
    ("blocked", CONTENT_REJECTED),
]

# Exception type names that indicate network-layer failures.
_NETWORK_ERROR_TYPES: frozenset[str] = frozenset({
    "ConnectTimeout",
    "RemoteProtocolError",
    "ConnectError",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "TimeoutException",
    "TimeoutError",
    "NetworkError",
    "ProtocolError",
    "ConnectionError",
})


def classify_publish_error(
    exception: Exception | None = None,
    reason: str = "",
) -> str:
    """Classify a publish failure into a structured error code.

    Parameters
    ----------
    exception:
        The exception that was raised, if any.  The type name and
        (for ``HTTPStatusError``) status code are inspected.
    reason:
        The error reason string from a ``PublishResult`` or exception
        message.  Matched against :data:`_REASON_PATTERNS` (case-
        insensitive).

    Returns
    -------
    str
        One of :data:`CREDENTIAL_EXPIRED`, :data:`RATE_LIMITED`,
        :data:`NETWORK_ERROR`, :data:`CONTENT_REJECTED`, or
        :data:`UNKNOWN`.
    """
    # 1. Check exception type for network errors (fast path).
    if exception is not None:
        exc_name: str = type(exception).__name__
        if exc_name in _NETWORK_ERROR_TYPES:
            return NETWORK_ERROR

        # httpx HTTPStatusError — check response status code.
        if exc_name == "HTTPStatusError":
            response = getattr(exception, "response", None)
            if response is not None:
                code: int = getattr(response, "status_code", 0)
                if code == 429:
                    return RATE_LIMITED
                if code in (401, 403):
                    return CREDENTIAL_EXPIRED

        # Fallback: use exception message for pattern matching.
        if not reason:
            reason = str(exception)

    # 2. Check reason string patterns (case-insensitive).
    reason_lower: str = reason.lower()
    for pattern, error_code in _REASON_PATTERNS:
        if pattern.lower() in reason_lower:
            return error_code

    return UNKNOWN


def build_error_result(
    platform: str,
    error_code: str,
    error_message: str,
    exception: Exception | None = None,
) -> PublishResult:
    """Build a structured error result dict for publish failures.

    The returned dict includes backward-compatible keys (``status``,
    ``platform``, ``reason``) alongside structured error metadata.

    Parameters
    ----------
    platform:
        Platform name.
    error_code:
        One of the canonical error codes.
    error_message:
        Human-readable error description.
    exception:
        Original exception, if any (for diagnostics).

    Returns
    -------
    dict
        Dict with ``status``, ``platform``, ``reason``, ``error_code``,
        ``error_message``, ``retryable``, and ``action`` keys.  When
        ``max_retries`` is not ``None`` it is included too.
    """
    retryable, max_retries, action = _ERROR_META.get(
        error_code,
        (False, None, "investigate"),
    )
    result: PublishResult = {  # type: ignore[typeddict-item]  # error_code, error_message, retryable, action are not defined in PublishResult TypedDict
        "status": "error",
        "platform": platform,
        "reason": error_message,
        "error_code": error_code,
        "error_message": error_message,
        "retryable": retryable,
        "action": action,
    }
    if max_retries is not None:
        result["max_retries"] = max_retries  # type: ignore[typeddict-item]  # max_retries not a defined PublishResult key
    if exception is not None:
        result["exception"] = type(exception).__name__  # type: ignore[typeddict-item]  # exception not a defined PublishResult key
    return result


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

#: Which error codes are eligible for automatic retry, and their budget.
_RETRY_BUDGET: dict[str, int] = {
    RATE_LIMITED: 3,
    NETWORK_ERROR: 2,
}


def _publish_with_retry(
    adapter: BasePlatformAdapter,
    artifact_dir: str,
    project: dict[str, Any],
    platform: str,
    refresh_fn: Callable[[], bool] | None = None,
) -> PublishResult:
    """Publish through *adapter* with automatic retry for transient errors.

    Retry policies:

    * ``rate_limited`` — exponential backoff (``2 ** attempt`` seconds),
      up to 3 retries.
    * ``network_error`` — exponential backoff, up to 2 retries.
    * ``credential_expired`` — triggers credential refresh via
      *refresh_fn* (max 1 attempt), then retries publish once.  When
      *refresh_fn* is ``None``, the error is returned directly with
      ``action: refresh_credential``.
    * ``credential_refresh_failed`` — returned when refresh also fails;
      requires human reconnection.
    * ``content_rejected`` / ``unknown`` — never retried.

    Parameters
    ----------
    adapter:
        The adapter instance to publish through.
    artifact_dir:
        Path to the rendered artifact directory.
    project:
        Full project dict.
    platform:
        Platform identifier for error reporting.
    refresh_fn:
        Optional callable that attempts credential refresh.  Return
        ``True`` on success, ``False`` on failure.  Only invoked for
        ``credential_expired`` errors, and at most once per publish.

    Returns
    -------
    dict
        Publish result — either the adapter's own success dict, or a
        structured error dict from :func:`build_error_result`.
    """
    last_reason: str = ""
    last_error_code: str = UNKNOWN
    retry_count: int = 0
    _refresh_attempted: bool = False

    while True:
        try:
            result = adapter.publish(artifact_dir, project)
        except Exception as exc:
            # Unknown adapter error — classify and decide retry strategy
            last_reason = str(exc)
            last_error_code = classify_publish_error(exception=exc)

            if last_error_code == CREDENTIAL_EXPIRED and _refresh_attempted:
                return build_error_result(
                    platform,
                    CREDENTIAL_REFRESH_FAILED,
                    f"Credential refresh failed for {platform}: {last_reason}",
                    exception=exc,
                )

            if (
                last_error_code == CREDENTIAL_EXPIRED
                and refresh_fn is not None
            ):
                _refresh_attempted = True
                if _try_credential_refresh(refresh_fn, platform):
                    log.info(
                        "publish.engine.refresh_retry",
                        platform=platform,
                    )
                    retry_count = 0
                    continue
                return build_error_result(
                    platform,
                    CREDENTIAL_REFRESH_FAILED,
                    f"Credential refresh failed for {platform}: {last_reason}",
                    exception=exc,
                )

            max_retries: int = _RETRY_BUDGET.get(last_error_code, 0)
            if max_retries == 0 or retry_count >= max_retries:
                log.warning(
                    "publish.engine.error",
                    platform=platform,
                    error_code=last_error_code,
                    error=last_reason,
                    retries=retry_count,
                )
                return build_error_result(
                    platform,
                    last_error_code,
                    last_reason,
                    exception=exc,
                )

            retry_count += 1
            delay: float = 2.0 ** retry_count
            log.info(
                "publish.engine.retry",
                platform=platform,
                error_code=last_error_code,
                attempt=retry_count,
                max_retries=max_retries,
                delay_s=delay,
            )
            time.sleep(delay)
            continue

        # No exception — inspect returned result.
        if result.get("status") == "ok":
            return result

        if result.get("status") != "error":
            # Non-standard status (not_implemented, draft_required, …)
            # passes through without retry wrapping.
            return result

        # Error result from adapter — classify and potentially retry.
        last_reason = str(result.get("reason", ""))
        last_error_code = classify_publish_error(reason=last_reason)

        if last_error_code == CREDENTIAL_EXPIRED and _refresh_attempted:
            return build_error_result(
                platform,
                CREDENTIAL_REFRESH_FAILED,
                f"Credential refresh failed for {platform}: {last_reason}",
            )

        if (
            last_error_code == CREDENTIAL_EXPIRED
            and refresh_fn is not None
        ):
            _refresh_attempted = True
            if _try_credential_refresh(refresh_fn, platform):
                log.info(
                    "publish.engine.refresh_retry",
                    platform=platform,
                )
                retry_count = 0
                continue
            return build_error_result(
                platform,
                CREDENTIAL_REFRESH_FAILED,
                f"Credential refresh failed for {platform}: {last_reason}",
            )

        max_retries = _RETRY_BUDGET.get(last_error_code, 0)
        if max_retries == 0 or retry_count >= max_retries:
            log.warning(
                "publish.engine.error",
                platform=platform,
                error_code=last_error_code,
                error=last_reason,
                retries=retry_count,
            )
            return build_error_result(platform, last_error_code, last_reason)

        retry_count += 1
        delay = 2.0 ** retry_count
        log.info(
            "publish.engine.retry",
            platform=platform,
            error_code=last_error_code,
            attempt=retry_count,
            max_retries=max_retries,
            delay_s=delay,
        )
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Credential refresh helpers
# ---------------------------------------------------------------------------


def _try_credential_refresh(
    refresh_fn: Callable[[], bool],
    platform: str,
) -> bool:
    """Invoke *refresh_fn* and return ``True`` on success.

    Catches any exception from the refresh function and logs it.
    """
    try:
        success = refresh_fn()
        if success:
            log.info("publish.engine.refresh.ok", platform=platform)
        else:
            log.warning("publish.engine.refresh.failed", platform=platform)
        return bool(success)
    except Exception as exc:
        # Catch-all for credential refresh function errors
        log.error(
            "publish.engine.refresh.error",
            platform=platform,
            error=str(exc),
        )
        return False


class PublishEngine:
    """Orchestrates publishing across every registered adapter.

    Usage::

        engine = PublishEngine()
        results = engine.publish_all("/path/to/artifact", project)
    """

    # Allow overriding the registry class for testing / extensibility.
    registry_class: type[AdapterRegistry] = AdapterRegistry

    @staticmethod
    def _resolve_automation(
        platform: str,
        automation: dict[str, str] | None,
    ) -> str:
        """Resolve the automation level for *platform*.

        Checks the explicit *automation* dict first, then falls back to
        :data:`AUTOMATION_DEFAULTS`, and finally returns ``"auto"`` for
        any unknown platform.
        """
        if automation and platform in automation:
            return automation[platform]
        return AUTOMATION_DEFAULTS.get(platform, _AUTO)

    def _refresh_credential(self, account_id: str) -> bool:
        """Attempt to refresh credentials for a platform account.

        Platform-specific logic:

        * **WeChat** (``oauth2_client_cred``): Loads appid + secret from
          the encrypted store and re-exchanges via
          :class:`OAuth2ClientCredentialsFlow`.  The new session token is
          cached in :class:`SessionManager`.
        * **Zhihu** (``cookie``): Cannot refresh programmatically — cookies
          require full re-authentication.
        * **Xiaohongshu** (``api_key``): Cannot refresh programmatically —
          keys require rotation by the user.

        Parameters
        ----------
        account_id:
            The account whose credentials to refresh.

        Returns
        -------
        bool
            ``True`` on successful refresh, ``False`` if the account is
            not found, the auth type is unsupported, or the refresh
            request itself failed.
        """
        from automedia.accounts.registry import AccountRegistry  # noqa: PLC0415

        registry = AccountRegistry()
        info = registry.get(account_id)
        if not info:
            log.warning(
                "publish.engine.refresh.account_not_found",
                account_id=account_id,
            )
            return False

        platform = info.get("platform", "")  # type: ignore[typeddict-item]  # AccountInfo TypedDict may not define 'platform' as optional get() key
        auth_type = info.get("auth_type", "")

        # --- oauth2_client_cred (WeChat) — re-exchange via stored creds ---
        if auth_type == "oauth2_client_cred":
            creds = registry.get_credentials(account_id)
            if not creds:
                log.warning(
                    "publish.engine.refresh.no_creds",
                    platform=platform,
                    account_id=account_id,
                )
                return False

            token_url = creds.get(
                "token_url",
                "https://api.weixin.qq.com/cgi-bin/token",
            )
            client_id = creds.get("client_id", creds.get("appid", ""))
            client_secret = creds.get(
                "client_secret", creds.get("secret", ""),
            )

            if not client_id or not client_secret:
                log.warning(
                    "publish.engine.refresh.missing_client_creds",
                    platform=platform,
                )
                return False

            try:
                from automedia.accounts.auth.oauth2 import (  # noqa: PLC0415
                    OAuth2ClientCredentialsFlow,
                )

                flow = OAuth2ClientCredentialsFlow()
                token = flow.exchange(
                    token_url=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                )

                from automedia.accounts.session import SessionManager  # noqa: PLC0415

                sm = SessionManager()
                sm.set_token(account_id, token)
                log.info(
                    "publish.engine.refresh.ok",
                    platform=platform,
                    account_id=account_id,
                )
                return True
            except Exception as exc:
                # Catch-all for OAuth2 flow / session store errors during refresh
                log.error(
                    "publish.engine.refresh.error",
                    platform=platform,
                    account_id=account_id,
                    error=str(exc),
                )
                return False

        # --- cookie (Zhihu) — cannot refresh programmatically ---
        if auth_type in ("cookie",):
            log.warning(
                "publish.engine.refresh.cookie_no_refresh",
                platform=platform,
                account_id=account_id,
            )
            return False

        # --- api_key / webhook_url (Xiaohongshu, Feishu) — cannot refresh ---
        if auth_type in ("api_key", "webhook_url"):
            log.warning(
                "publish.engine.refresh.key_no_refresh",
                platform=platform,
                account_id=account_id,
            )
            return False

        # --- unsupported auth type ---
        log.warning(
            "publish.engine.refresh.unsupported_auth",
            auth_type=auth_type,
            platform=platform,
        )
        return False

    def publish_all(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        account_ids: list[str] | None = None,
        automation: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Iterate adapters and publish.

        When *account_ids* is provided, publishes only to those accounts
        (instantiating adapters with account context).  Falls back to legacy
        behavior when ``None``.

        Partial failure: each account publish is independent; failures on
        one account don't block others.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.
        project:
            Full project dict.
        account_ids:
            Optional list of account identifiers for PRD-4 account-aware
            publishing.
        automation:
            Optional per-platform automation levels
            (e.g. ``{"wechat": "auto", "zhihu": "review"}``).  When
            ``None`` or missing a platform, :data:`AUTOMATION_DEFAULTS`
            are used.

        Returns
        -------
        dict[str, Any]
            Mapping ``{platform_or_account_id -> result_dict}`` for every
            adapter that was actually invoked.  Error results include
            additional structured fields (``error_code``, ``retryable``,
            ``action``).
        """
        results: dict[str, Any] = {}

        if account_ids:
            # PRD-4 path: publish per-account
            from automedia.accounts.registry import AccountRegistry  # noqa: PLC0415

            registry = AccountRegistry()

            for account_id in account_ids:
                info = registry.get(account_id)
                if not info:
                    results[account_id] = {
                        "status": "error",
                        "reason": f"Account not found: {account_id}",
                    }
                    continue

                platform: str = info["platform"]

                # ---- automation check ---------------------------------
                level = self._resolve_automation(platform, automation)
                if level == _MANUAL:
                    results[account_id] = {
                        "status": "skipped",
                        "platform": platform,
                        "reason": "automation level: manual",
                    }
                    continue
                # auto / review → validate and publish
                try:
                    adapter_cls = self.registry_class.get(platform)
                    adapter: BasePlatformAdapter = adapter_cls(account_id=account_id)

                    if not adapter.validate(artifact_dir):
                        results[account_id] = {
                            "status": "skipped",
                            "reason": "validation failed",
                        }
                        continue

                    if level == _REVIEW:
                        result = adapter.publish(
                            artifact_dir, project, draft_only=True,
                        )
                    else:
                        refresh_fn: Callable[[], bool] | None = (
                            lambda aid=account_id: self._refresh_credential(aid)
                        )
                        result = _publish_with_retry(
                            adapter, artifact_dir, project, platform,
                            refresh_fn=refresh_fn,
                        )
                    results[account_id] = result
                except Exception as exc:
                    # Catch-all for per-account adapter instantiation/publish errors
                    results[account_id] = {"status": "error", "reason": str(exc)}
        else:
            # Legacy path: platform-based publishing
            for name in self.registry_class.list():
                adapter_cls = self.registry_class.get(name)
                adapter = adapter_cls()

                if not adapter.enabled:
                    continue

                # ---- automation check ---------------------------------
                level = self._resolve_automation(name, automation)
                if level == _MANUAL:
                    results[name] = {
                        "status": "skipped",
                        "platform": name,
                        "reason": "automation level: manual",
                    }
                    continue
                # auto / review → validate and publish
                if not adapter.validate(artifact_dir):
                    results[name] = {
                        "status": "skipped",
                        "reason": "validation failed",
                    }
                    continue

                try:
                    if level == _REVIEW:
                        result = adapter.publish(
                            artifact_dir, project, draft_only=True,
                        )
                    else:
                        result = _publish_with_retry(
                            adapter, artifact_dir, project, name,
                        )
                    results[name] = result
                except Exception as exc:
                    # Catch-all for legacy adapter publish errors
                    results[name] = {"status": "error", "reason": str(exc)}

        return results
