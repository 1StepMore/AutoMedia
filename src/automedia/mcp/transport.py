"""MCP 传输层配置与鉴权（health-assessment P1-1）。

中文说明：MCP 服务默认走 **stdio**——而 stdio 下**没有可服务端校验的凭证通道**：
``initialize`` 握手只携带客户端自报的 ``clientInfo``（可被任意编造），因此
"传输层鉴权"只能在 HTTP 形态下成立。本模块提供三件事：

* :func:`resolve_transport_config` —— 从环境变量解析传输形态，默认 stdio
  （既有部署零行为变更）；
* :class:`_EnvTokenVerifier` —— Bearer token 校验（``secrets.compare_digest``
  常量时间比较，token 来自 ``AUTOMEDIA_MCP_AUTH_TOKEN``）；
* :func:`fastmcp_transport_kwargs` —— 把上述两件套交给
  ``FastMCP(auth=..., token_verifier=...)``。

**安全姿态（fail-closed）**：选择 HTTP 却未配置 token 时**拒绝启动**。一个无鉴权
的 HTTP MCP 端点暴露面远大于 stdio，把"无鉴权 HTTP"作为静默默认值是这里最危险的
可能性，因此宁可启动失败并给出配置指引。
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from structlog import get_logger

if TYPE_CHECKING:
    from mcp.server.auth.provider import AccessToken

log = get_logger(__name__)

TransportName = Literal["stdio", "streamable-http"]

STDIO_TRANSPORT: TransportName = "stdio"
HTTP_TRANSPORT: TransportName = "streamable-http"
SUPPORTED_TRANSPORTS: tuple[str, ...] = (STDIO_TRANSPORT, HTTP_TRANSPORT)

_ENV_TRANSPORT = "AUTOMEDIA_MCP_TRANSPORT"
_ENV_HOST = "AUTOMEDIA_MCP_HOST"
_ENV_PORT = "AUTOMEDIA_MCP_PORT"
_ENV_TOKEN = "AUTOMEDIA_MCP_AUTH_TOKEN"  # noqa: S105 — env var *name*, not a secret value

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

#: 鉴权通过后授予的 scope（本服务只区分"能否进入"，不做细粒度授权）。
AUTH_SCOPE = "automedia:mcp"


@dataclass(frozen=True)
class TransportConfig:
    """解析后的传输配置。

    Attributes:
        transport: ``"stdio"`` 或 ``"streamable-http"``。
        host: HTTP 监听地址（仅 HTTP 形态使用）。
        port: HTTP 监听端口（仅 HTTP 形态使用）。
        auth_token: Bearer token；空串表示未配置。
    """

    transport: TransportName = STDIO_TRANSPORT
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    auth_token: str = ""

    @property
    def is_http(self) -> bool:
        """是否为 HTTP 形态（HTTP 形态必须已配置 token）。"""
        return self.transport == HTTP_TRANSPORT


class _EnvTokenVerifier:
    """Bearer token 校验器：与配置的 token 做常量时间比较。

    中文说明：实现 MCP 的 ``TokenVerifier`` 协议（只要求 ``verify_token``）。
    常量时间比较避免通过响应时间侧信道逐字节猜测 token。

    Args:
        expected_token: 期望的 token；空串视为配置错误。
    """

    def __init__(self, expected_token: str) -> None:
        if not expected_token:
            raise ValueError("expected_token must not be empty")
        self._expected = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        """校验 bearer token。

        Args:
            token: 客户端在 ``Authorization: Bearer <token>`` 中提供的值。

        Returns:
            通过则返回 :class:`AccessToken`；不通过返回 ``None``（HTTP 层转 401）。
        """
        if not token or not secrets.compare_digest(token, self._expected):
            log.warning("mcp.auth.rejected", reason="token mismatch")
            return None

        from mcp.server.auth.provider import AccessToken

        return AccessToken(
            token=token,
            client_id="automedia-mcp-client",
            scopes=[AUTH_SCOPE],
        )


def resolve_transport_config(env: Mapping[str, str] | None = None) -> TransportConfig:
    """从环境变量解析传输配置。

    Args:
        env: 环境变量映射；``None`` 表示读取 ``os.environ``（测试可注入）。

    Returns:
        :class:`TransportConfig`；默认 ``stdio`` + ``127.0.0.1:8000``。

    Raises:
        ValueError: 传输值不受支持；或选择了 HTTP 但未配置 ``AUTOMEDIA_MCP_AUTH_TOKEN``；
            或端口不是整数。
    """
    values: Mapping[str, str] = os.environ if env is None else env

    transport_name = (values.get(_ENV_TRANSPORT, "") or STDIO_TRANSPORT).strip().lower()
    if transport_name not in SUPPORTED_TRANSPORTS:
        expected = ", ".join(SUPPORTED_TRANSPORTS)
        raise ValueError(
            f"unsupported {_ENV_TRANSPORT}={transport_name!r}; expected one of {expected}"
        )
    transport = cast("TransportName", transport_name)

    token = (values.get(_ENV_TOKEN, "") or "").strip()
    if transport == HTTP_TRANSPORT and not token:
        raise ValueError(
            f"{_ENV_TRANSPORT}={HTTP_TRANSPORT} requires {_ENV_TOKEN} — "
            "an unauthenticated HTTP endpoint is not a supported configuration. "
            "Set the token, or keep the default stdio transport."
        )

    host = (values.get(_ENV_HOST, "") or DEFAULT_HOST).strip()
    raw_port = (values.get(_ENV_PORT, "") or "").strip()
    if raw_port:
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError(f"{_ENV_PORT} must be an integer, got {raw_port!r}") from exc
    else:
        port = DEFAULT_PORT

    return TransportConfig(transport=transport, host=host, port=port, auth_token=token)


def fastmcp_transport_kwargs(config: TransportConfig) -> dict[str, Any]:
    """按传输形态返回 ``FastMCP`` 的构造参数。

    中文说明：stdio 形态**不注入任何鉴权参数**——它没有可校验的凭证通道，
    注入只会造成"以为有鉴权"的错觉；HTTP 形态同时注入 ``host``/``port``。

    Args:
        config: 已解析的传输配置。

    Returns:
        stdio ⇒ ``{}``；HTTP ⇒ ``auth`` / ``token_verifier`` / ``host`` / ``port``。
    """
    if not config.is_http:
        return {}

    from mcp.server.auth.settings import AuthSettings
    from pydantic import AnyHttpUrl

    base_url = f"http://{config.host}:{config.port}"
    return {
        "host": config.host,
        "port": config.port,
        "auth": AuthSettings(
            issuer_url=AnyHttpUrl(base_url),
            resource_server_url=AnyHttpUrl(base_url),
        ),
        "token_verifier": _EnvTokenVerifier(config.auth_token),
    }
