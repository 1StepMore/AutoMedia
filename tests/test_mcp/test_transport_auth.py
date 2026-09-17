"""MCP 传输层配置与 Bearer 鉴权的锁定测试（health-assessment P1-1）。

中文说明：MCP 默认走 stdio（无凭证通道，故不注入任何鉴权）；HTTP 形态必须
配置 ``AUTOMEDIA_MCP_AUTH_TOKEN``，否则**拒绝启动**（fail-closed）。本文件锁定
三件事：解析规则、token 校验语义、以及"stdio 默认路径零变更"。
"""

from __future__ import annotations

import asyncio

import pytest

from automedia.mcp.transport import (
    AUTH_SCOPE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    HTTP_TRANSPORT,
    STDIO_TRANSPORT,
    TransportConfig,
    _EnvTokenVerifier,
    fastmcp_transport_kwargs,
    resolve_transport_config,
)


class TestResolveTransportConfig:
    """环境变量解析（默认值、fail-closed、非法输入）。"""

    def test_defaults_to_stdio(self) -> None:
        """未设置任何变量 ⇒ stdio + 默认 host/port + 无 token。"""
        config = resolve_transport_config({})

        assert config.transport == STDIO_TRANSPORT
        assert config.host == DEFAULT_HOST
        assert config.port == DEFAULT_PORT
        assert config.auth_token == ""
        assert config.is_http is False

    def test_http_without_token_refuses_to_start(self) -> None:
        """HTTP 形态缺 token ⇒ 抛 ``ValueError``（绝不静默降级为无鉴权 HTTP）。"""
        with pytest.raises(ValueError, match="AUTOMEDIA_MCP_AUTH_TOKEN"):
            resolve_transport_config({"AUTOMEDIA_MCP_TRANSPORT": HTTP_TRANSPORT})

    def test_http_with_token(self) -> None:
        config = resolve_transport_config(
            {
                "AUTOMEDIA_MCP_TRANSPORT": "streamable-http",
                "AUTOMEDIA_MCP_AUTH_TOKEN": "s3cret",
                "AUTOMEDIA_MCP_HOST": "192.168.1.10",
                "AUTOMEDIA_MCP_PORT": "9100",
            }
        )

        assert config.transport == HTTP_TRANSPORT
        assert config.is_http is True
        assert config.host == "192.168.1.10"
        assert config.port == 9100
        assert config.auth_token == "s3cret"

    def test_unsupported_transport_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            resolve_transport_config({"AUTOMEDIA_MCP_TRANSPORT": "websocket"})

    def test_non_integer_port_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an integer"):
            resolve_transport_config({"AUTOMEDIA_MCP_PORT": "http"})

    def test_transport_value_is_case_insensitive(self) -> None:
        config = resolve_transport_config({"AUTOMEDIA_MCP_TRANSPORT": "Stdio"})
        assert config.transport == STDIO_TRANSPORT


class TestEnvTokenVerifier:
    """Bearer token 校验语义。"""

    def test_accepts_matching_token(self) -> None:
        verifier = _EnvTokenVerifier("s3cret")
        token = asyncio.run(verifier.verify_token("s3cret"))

        assert token is not None
        assert token.client_id == "automedia-mcp-client"
        assert token.scopes == [AUTH_SCOPE]

    @pytest.mark.parametrize("bad", ["", "wrong", "s3cre", "s3cret "])
    def test_rejects_non_matching_token(self, bad: str) -> None:
        verifier = _EnvTokenVerifier("s3cret")
        assert asyncio.run(verifier.verify_token(bad)) is None

    def test_empty_expected_token_is_a_config_error(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            _EnvTokenVerifier("")


class TestFastmcpTransportKwargs:
    """``FastMCP`` 构造参数：stdio 零注入，HTTP 注入鉴权与监听地址。"""

    def test_stdio_injects_nothing(self) -> None:
        """stdio ⇒ ``{}`` —— 既有部署与 52 处 ``create_server()`` 调用零变更。"""
        assert fastmcp_transport_kwargs(TransportConfig()) == {}

    def test_http_injects_auth_and_binding(self) -> None:
        kwargs = fastmcp_transport_kwargs(
            TransportConfig(transport=HTTP_TRANSPORT, host="127.0.0.1", port=8123, auth_token="t")
        )

        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8123
        assert isinstance(kwargs["token_verifier"], _EnvTokenVerifier)
        # auth 与 token_verifier 必须成对（FastMCP 的装配契约）
        assert kwargs["auth"] is not None
        assert str(kwargs["auth"].issuer_url).startswith("http://127.0.0.1:8123")


class TestCreateServerUnchanged:
    """默认（stdio）下 ``create_server()`` 仍可构造，且不携带鉴权。"""

    def test_create_server_still_works(self) -> None:
        from automedia.mcp.server import create_server

        server = create_server()

        assert len(server._tool_manager._tools) == 68
        assert getattr(server, "_token_verifier", None) is None
        assert getattr(server.settings, "auth", None) is None
