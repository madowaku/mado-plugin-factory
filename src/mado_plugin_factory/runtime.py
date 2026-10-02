from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .extensions import compile_extension_capabilities

SCHEMA_VERSION = "0.1"
MODERN_PROTOCOL = "2026-07-28"
LEGACY_PROTOCOL = "2025-11-25"
DEFAULT_TIMEOUT = 5.0
DEFAULT_EVIDENCE_DIR = "evidence/runtime/extensions"

DIRECTLY_PROBEABLE = {
    "sidebar_app",
    "conversation_panel",
    "plugin_settings",
    "file_viewer_editor",
    "display_modes",
    "composer_mentions",
}
HOST_REQUIRED = {
    "deep_links",
    "model_app_context",
    "rich_forms",
}
PACKAGE_ONLY = {"plugin_onboarding"}


class RuntimeSmokeError(ValueError):
    pass


class UnsafeCanaryToolError(RuntimeSmokeError):
    pass


def run_extension_runtime_smoke(
    root: Path,
    *,
    server: str | None = None,
    mode: str = "auto",
    timeout: float = DEFAULT_TIMEOUT,
    write_evidence: bool = False,
    evidence_output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeSmokeError(f"candidate path is not a directory: {root}")
    if mode not in {"auto", "modern", "legacy"}:
        raise RuntimeSmokeError("mode must be auto, modern, or legacy")
    if timeout <= 0:
        raise RuntimeSmokeError("timeout must be greater than zero")

    manifest_path, config = _load_mcp_config(root)
    server_name, declaration = _select_server(config, server)
    transport = _transport_kind(declaration)

    static = compile_extension_capabilities(root)
    expected = sorted(
        item["id"]
        for item in static["capabilities"]
        if item["status"] == "detected"
    )

    started = time.monotonic()
    if transport == "stdio":
        runtime = _probe_stdio(
            root,
            declaration,
            mode=mode,
            timeout=timeout,
        )
    elif transport == "streamable-http":
        runtime = _probe_http_modern(
            declaration,
            mode=mode,
            timeout=timeout,
        )
    else:
        raise RuntimeSmokeError(f"unsupported MCP transport: {transport}")
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)

    checks = _evaluate_extensions(
        expected,
        runtime["discover"],
        runtime["tools"],
        runtime["resources"],
    )

    missing = sorted(
        item["id"]
        for item in checks
        if item["state"] == "missing"
    )
    host_required = sorted(
        item["id"]
        for item in checks
        if item["state"] == "host_required"
    )
    verified = sorted(
        item["id"]
        for item in checks
        if item["state"] == "verified"
    )
    probeable_expected = sorted(
        extension_id
        for extension_id in expected
        if extension_id in DIRECTLY_PROBEABLE
    )

    runtime_smoke_passed = (
        runtime["connected"]
        and not missing
        and all(
            extension_id in verified
            for extension_id in probeable_expected
        )
    )
    runtime_verified = bool(
        runtime_smoke_passed
        and probeable_expected
        and not host_required
    )

    tool_observations = sorted(
        (_tool_observation(tool) for tool in runtime["tools"]),
        key=lambda item: item.get("name") or "",
    )
    fingerprint = _runtime_fingerprint(
        protocol_version=runtime["protocol_version"],
        era=runtime["era"],
        discover=runtime["discover"],
        tools=tool_observations,
        resources=runtime["resource_observations"],
    )

    smoke_id = _smoke_id(
        server_name,
        runtime["protocol_version"],
        expected,
        runtime["tool_names"],
        runtime["resource_uris"],
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "smoke_id": smoke_id,
        "source": {
            "root": str(root),
            "mcp_manifest": manifest_path.relative_to(root).as_posix(),
            "server": server_name,
            "transport": transport,
        },
        "protocol": {
            "requested_mode": mode,
            "negotiated_version": runtime["protocol_version"],
            "era": runtime["era"],
        },
        "execution": {
            "connected": runtime["connected"],
            "elapsed_ms": elapsed_ms,
        },
        "server_info": runtime["server_info"],
        "observations": {
            "tool_count": len(runtime["tools"]),
            "tool_names": runtime["tool_names"],
            "tools": tool_observations,
            "resource_uris": runtime["resource_uris"],
            "resources": runtime["resource_observations"],
        },
        "runtime_fingerprint": fingerprint,
        "expected_extensions": expected,
        "extension_checks": checks,
        "verified_extensions": verified,
        "host_required_extensions": host_required,
        "missing_extensions": missing,
        "runtime_smoke_passed": runtime_smoke_passed,
        "runtime_verified": runtime_verified,
        "runtime_scope": "mcp_server",
        "warnings": _warnings(
            expected=expected,
            host_required=host_required,
            transport=transport,
            mode=mode,
        ),
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/{server_name}-{smoke_id}.json"
        )
        result["evidence_output"] = _write_evidence(
            root,
            result,
            output=output,
            force=force,
        )
    return result



def execute_mcp_tool_canary(
    root: Path,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    server: str | None = None,
    mode: str = "auto",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Execute one MCP tool call for behavioral contract replay."""
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeSmokeError(
            f"candidate path is not a directory: {root}"
        )
    if mode not in {"auto", "modern", "legacy"}:
        raise RuntimeSmokeError(
            "mode must be auto, modern, or legacy"
        )
    if timeout <= 0:
        raise RuntimeSmokeError(
            "timeout must be greater than zero"
        )
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise RuntimeSmokeError(
            "tool_name must be a non-empty string"
        )
    if not isinstance(arguments, dict):
        raise RuntimeSmokeError(
            "tool arguments must be an object"
        )

    _manifest_path, config = _load_mcp_config(root)
    server_name, declaration = _select_server(
        config,
        server,
    )
    transport = _transport_kind(declaration)

    if transport == "stdio":
        observed = _call_tool_stdio(
            root,
            declaration,
            tool_name=tool_name,
            arguments=arguments,
            mode=mode,
            timeout=timeout,
        )
    elif transport == "streamable-http":
        observed = _call_tool_http(
            declaration,
            tool_name=tool_name,
            arguments=arguments,
            mode=mode,
            timeout=timeout,
        )
    else:
        raise RuntimeSmokeError(
            f"unsupported MCP transport: {transport}"
        )

    return {
        "server": server_name,
        "transport": transport,
        **observed,
    }


def _call_tool_stdio(
    root: Path,
    declaration: dict[str, Any],
    *,
    tool_name: str,
    arguments: dict[str, Any],
    mode: str,
    timeout: float,
) -> dict[str, Any]:
    if mode in {"auto", "modern"}:
        client = _StdioClient(root, declaration, timeout)
        try:
            discover = client.request(
                "server/discover",
                {},
                modern=True,
            )
            if "result" in discover:
                return _execute_tool_with_client(
                    client,
                    tool_name=tool_name,
                    arguments=arguments,
                    protocol_version=MODERN_PROTOCOL,
                    era="modern",
                    modern=True,
                )
            if mode == "modern":
                raise RuntimeSmokeError(
                    "server/discover failed: "
                    + _rpc_error_text(discover)
                )
        finally:
            client.close()

    client = _StdioClient(root, declaration, timeout)
    try:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": LEGACY_PROTOCOL,
                "capabilities": {},
                "clientInfo": {
                    "name": "mado-plugin-factory",
                    "version": "1.5.0",
                },
            },
            modern=False,
        )
        if "result" not in initialize:
            raise RuntimeSmokeError(
                "initialize failed: "
                + _rpc_error_text(initialize)
            )
        client.notify("notifications/initialized")
        result = initialize["result"]
        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str):
            negotiated = LEGACY_PROTOCOL
        return _execute_tool_with_client(
            client,
            tool_name=tool_name,
            arguments=arguments,
            protocol_version=negotiated,
            era="legacy",
            modern=False,
        )
    finally:
        client.close()


def _call_tool_http(
    declaration: dict[str, Any],
    *,
    tool_name: str,
    arguments: dict[str, Any],
    mode: str,
    timeout: float,
) -> dict[str, Any]:
    if mode == "legacy":
        raise RuntimeSmokeError(
            "legacy streamable-http is not supported by M1.5"
        )
    client = _ModernHttpClient(declaration, timeout)
    discover = client.request(
        "server/discover",
        {},
        modern=True,
    )
    if "result" not in discover:
        raise RuntimeSmokeError(
            "server/discover failed: "
            + _rpc_error_text(discover)
        )
    return _execute_tool_with_client(
        client,
        tool_name=tool_name,
        arguments=arguments,
        protocol_version=MODERN_PROTOCOL,
        era="modern",
        modern=True,
    )


def _execute_tool_with_client(
    client: Any,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    protocol_version: str,
    era: str,
    modern: bool,
) -> dict[str, Any]:
    tools_message = client.request(
        "tools/list",
        {},
        modern=modern,
    )
    if "result" not in tools_message:
        raise RuntimeSmokeError(
            "tools/list failed: "
            + _rpc_error_text(tools_message)
        )
    raw_tools = tools_message["result"].get("tools", [])
    tools = [
        item
        for item in raw_tools
        if isinstance(item, dict)
    ] if isinstance(raw_tools, list) else []
    descriptor = next(
        (
            item
            for item in tools
            if item.get("name") == tool_name
        ),
        None,
    )
    if descriptor is None:
        raise RuntimeSmokeError(
            f"MCP tool not found: {tool_name}"
        )
    annotations = descriptor.get("annotations")
    if not (
        isinstance(annotations, dict)
        and annotations.get("readOnlyHint") is True
    ):
        raise UnsafeCanaryToolError(
            f"canary refuses tool without annotations.readOnlyHint=true: {tool_name}"
        )

    message = client.request(
        "tools/call",
        {
            "name": tool_name,
            "arguments": arguments,
        },
        modern=modern,
    )
    return {
        "protocol_version": protocol_version,
        "era": era,
        "descriptor": descriptor,
        "message": message,
    }


def _load_mcp_config(root: Path) -> tuple[Path, dict[str, Any]]:
    for name in ("mcp.json", ".mcp.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeSmokeError(
                f"unable to read MCP config at {path}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeSmokeError("MCP config must be a JSON object")
        servers = value.get("mcpServers")
        if not isinstance(servers, dict) or not servers:
            raise RuntimeSmokeError("MCP config has no configured mcpServers")
        return path, value
    raise RuntimeSmokeError("no mcp.json or .mcp.json found")


def _select_server(
    config: dict[str, Any],
    requested: str | None,
) -> tuple[str, dict[str, Any]]:
    servers = config.get("mcpServers")
    assert isinstance(servers, dict)
    if requested is not None:
        declaration = servers.get(requested)
        if not isinstance(declaration, dict):
            raise RuntimeSmokeError(f"MCP server not found: {requested}")
        return requested, declaration

    names = sorted(
        name
        for name, declaration in servers.items()
        if isinstance(name, str) and isinstance(declaration, dict)
    )
    if len(names) != 1:
        raise RuntimeSmokeError(
            "select an MCP server with --server when more than one is configured"
        )
    return names[0], servers[names[0]]


def _transport_kind(declaration: dict[str, Any]) -> str:
    raw = declaration.get("type")
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"stdio", "streamable-http"}:
            return normalized
        if normalized in {"http", "sse"} and declaration.get("url"):
            return "streamable-http"
    if isinstance(declaration.get("command"), str):
        return "stdio"
    if isinstance(declaration.get("url"), str):
        return "streamable-http"
    raise RuntimeSmokeError(
        "MCP server declaration needs command/args or a streamable-http url"
    )


class _StdioClient:
    def __init__(
        self,
        root: Path,
        declaration: dict[str, Any],
        timeout: float,
    ) -> None:
        command = declaration.get("command")
        if not isinstance(command, str) or not command.strip():
            raise RuntimeSmokeError("stdio MCP server requires command")
        args = declaration.get("args") or []
        if not isinstance(args, list) or not all(
            isinstance(item, str) for item in args
        ):
            raise RuntimeSmokeError("stdio MCP args must be a list of strings")

        cwd = root
        raw_cwd = declaration.get("cwd")
        if isinstance(raw_cwd, str) and raw_cwd.strip():
            cwd = _safe_relative(root, raw_cwd, label="MCP cwd")
            if not cwd.is_dir():
                raise RuntimeSmokeError(f"MCP cwd does not exist: {cwd}")

        env = os.environ.copy()
        raw_env = declaration.get("env")
        if isinstance(raw_env, dict):
            for key, value in raw_env.items():
                if isinstance(key, str) and isinstance(value, str):
                    env[key] = value

        self.timeout = timeout
        try:
            self.process = subprocess.Popen(
                [command, *args],
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as exc:
            raise RuntimeSmokeError(
                f"unable to start MCP server command {command!r}: {exc}"
            ) from exc

        self._queue: queue.Queue[str | None] = queue.Queue()
        self._reader = threading.Thread(
            target=self._read_stdout,
            daemon=True,
        )
        self._reader.start()
        self._next_id = 1

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self._queue.put(line)
        finally:
            self._queue.put(None)

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        modern: bool,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        resolved = dict(params or {})
        if modern:
            resolved.setdefault(
                "_meta",
                _modern_meta(),
            )
        if resolved:
            payload["params"] = resolved
        self._send(payload)

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeSmokeError(
                    f"MCP request timed out: {method}"
                )
            try:
                line = self._queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise RuntimeSmokeError(
                    f"MCP request timed out: {method}"
                ) from exc
            if line is None:
                stderr = self._stderr_tail()
                raise RuntimeSmokeError(
                    "MCP stdio server closed before responding"
                    + (f": {stderr}" if stderr else "")
                )
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("id") != request_id:
                continue
            return message

    def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            payload["params"] = params
        self._send(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise RuntimeSmokeError("MCP stdio server is not running")
        assert self.process.stdin is not None
        self.process.stdin.write(
            json.dumps(payload, ensure_ascii=False) + "\n"
        )
        self.process.stdin.flush()

    def _stderr_tail(self) -> str:
        if self.process.poll() is None or self.process.stderr is None:
            return ""
        try:
            text = self.process.stderr.read()
        except OSError:
            return ""
        return text.strip()[-500:]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)


def _probe_stdio(
    root: Path,
    declaration: dict[str, Any],
    *,
    mode: str,
    timeout: float,
) -> dict[str, Any]:
    if mode in {"auto", "modern"}:
        client = _StdioClient(root, declaration, timeout)
        try:
            discover = client.request(
                "server/discover",
                {},
                modern=True,
            )
            if "result" in discover:
                return _collect_runtime(
                    client,
                    discover_result=discover["result"],
                    protocol_version=MODERN_PROTOCOL,
                    era="modern",
                    modern=True,
                )
            if mode == "modern":
                raise RuntimeSmokeError(
                    "server/discover failed: "
                    + _rpc_error_text(discover)
                )
        finally:
            client.close()

    client = _StdioClient(root, declaration, timeout)
    try:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": LEGACY_PROTOCOL,
                "capabilities": {
                    "extensions": {
                        "openai/elicitation": {
                            "form": {}
                        }
                    }
                },
                "clientInfo": {
                    "name": "mado-plugin-factory",
                    "version": "0.9.0",
                },
            },
            modern=False,
        )
        if "result" not in initialize:
            raise RuntimeSmokeError(
                "initialize failed: " + _rpc_error_text(initialize)
            )
        client.notify("notifications/initialized")
        result = initialize["result"]
        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str):
            negotiated = LEGACY_PROTOCOL
        return _collect_runtime(
            client,
            discover_result=result,
            protocol_version=negotiated,
            era="legacy",
            modern=False,
        )
    finally:
        client.close()


class _ModernHttpClient:
    def __init__(
        self,
        declaration: dict[str, Any],
        timeout: float,
    ) -> None:
        url = declaration.get("url")
        if not isinstance(url, str) or not url.strip():
            raise RuntimeSmokeError(
                "streamable-http MCP server requires url"
            )
        self.url = url
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MODERN_PROTOCOL,
        }

        raw_headers = declaration.get("http_headers")
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                if isinstance(key, str) and isinstance(value, str):
                    self.headers[key] = value

        bearer_env = declaration.get("bearer_token_env_var")
        if isinstance(bearer_env, str) and bearer_env:
            token = os.environ.get(bearer_env)
            if not token:
                raise RuntimeSmokeError(
                    f"required bearer token environment variable is missing: {bearer_env}"
                )
            self.headers["Authorization"] = f"Bearer {token}"
        self._next_id = 1

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        modern: bool = True,
    ) -> dict[str, Any]:
        if not modern:
            raise RuntimeSmokeError(
                "legacy streamable-http is not supported by M0.9; use a modern MCP 2026-07-28 endpoint"
            )
        request_id = self._next_id
        self._next_id += 1
        resolved = dict(params or {})
        resolved.setdefault("_meta", _modern_meta())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": resolved,
        }
        headers = dict(self.headers)
        headers["Mcp-Method"] = method
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers.get(
                    "Content-Type",
                    "",
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeSmokeError(
                f"MCP HTTP {method} failed with {exc.code}: {body[:300]}"
            ) from exc
        except OSError as exc:
            raise RuntimeSmokeError(
                f"MCP HTTP {method} failed: {exc}"
            ) from exc
        return _parse_http_message(body, content_type, request_id)

    def close(self) -> None:
        return None


def _probe_http_modern(
    declaration: dict[str, Any],
    *,
    mode: str,
    timeout: float,
) -> dict[str, Any]:
    if mode == "legacy":
        raise RuntimeSmokeError(
            "legacy streamable-http is not supported by M0.9; use a modern MCP 2026-07-28 endpoint"
        )
    client = _ModernHttpClient(declaration, timeout)
    discover = client.request(
        "server/discover",
        {},
        modern=True,
    )
    if "result" not in discover:
        raise RuntimeSmokeError(
            "server/discover failed: " + _rpc_error_text(discover)
        )
    return _collect_runtime(
        client,
        discover_result=discover["result"],
        protocol_version=MODERN_PROTOCOL,
        era="modern",
        modern=True,
    )


def _collect_runtime(
    client: Any,
    *,
    discover_result: dict[str, Any],
    protocol_version: str,
    era: str,
    modern: bool,
) -> dict[str, Any]:
    tools_message = client.request(
        "tools/list",
        {},
        modern=modern,
    )
    if "result" not in tools_message:
        raise RuntimeSmokeError(
            "tools/list failed: " + _rpc_error_text(tools_message)
        )
    tools_result = tools_message["result"]
    tools = tools_result.get("tools", [])
    if not isinstance(tools, list):
        raise RuntimeSmokeError("tools/list result.tools must be a list")
    tools = [item for item in tools if isinstance(item, dict)]

    resource_uris = sorted(
        {
            uri
            for tool in tools
            for uri in [_tool_resource_uri(tool)]
            if uri
        }
    )
    resources: dict[str, dict[str, Any]] = {}
    for uri in resource_uris:
        message = client.request(
            "resources/read",
            {"uri": uri},
            modern=modern,
        )
        if "result" not in message:
            resources[uri] = {
                "ok": False,
                "error": _rpc_error_text(message),
            }
            continue
        resources[uri] = _resource_observation(
            uri,
            message["result"],
        )

    return {
        "connected": True,
        "protocol_version": protocol_version,
        "era": era,
        "discover": discover_result,
        "server_info": _server_info(discover_result, era),
        "tools": tools,
        "tool_names": sorted(
            str(item.get("name"))
            for item in tools
            if item.get("name")
        ),
        "resource_uris": resource_uris,
        "resources": resources,
        "resource_observations": [
            {"uri": uri, **observation}
            for uri, observation in sorted(resources.items())
        ],
    }


def _evaluate_extensions(
    expected: list[str],
    discover: dict[str, Any],
    tools: list[dict[str, Any]],
    resources: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    checks = []
    for extension_id in expected:
        if extension_id in HOST_REQUIRED:
            checks.append(
                {
                    "id": extension_id,
                    "state": "host_required",
                    "reason": "requires ChatGPT host or MCP App interaction beyond server metadata probing",
                }
            )
            continue
        if extension_id in PACKAGE_ONLY:
            checks.append(
                {
                    "id": extension_id,
                    "state": "package_only",
                    "reason": "onboarding is a package/host surface, not an MCP server runtime surface",
                }
            )
            continue

        verified, evidence = _verify_probeable(
            extension_id,
            discover,
            tools,
            resources,
        )
        checks.append(
            {
                "id": extension_id,
                "state": "verified" if verified else "missing",
                "evidence": evidence,
            }
        )
    return checks


def _verify_probeable(
    extension_id: str,
    discover: dict[str, Any],
    tools: list[dict[str, Any]],
    resources: dict[str, dict[str, Any]],
) -> tuple[bool, list[str]]:
    if extension_id == "plugin_settings":
        settings = _settings_capability(discover)
        if not settings:
            return False, []
        read_tool = settings.get("readTool")
        update_tool = settings.get("updateTool")
        names = {item.get("name") for item in tools}
        ok = (
            isinstance(read_tool, str)
            and isinstance(update_tool, str)
            and read_tool in names
            and update_tool in names
        )
        evidence = [
            "server.capabilities.extensions.openai/settings",
            f"tool:{read_tool}" if isinstance(read_tool, str) else "",
            f"tool:{update_tool}" if isinstance(update_tool, str) else "",
        ]
        return ok, [item for item in evidence if item]

    if extension_id == "composer_mentions":
        names = []
        for tool in tools:
            meta = _tool_meta(tool)
            ext = meta.get("openai/extensions")
            ui = meta.get("ui")
            mention = (
                ext.get("mentions/search")
                if isinstance(ext, dict)
                else None
            )
            visibility = (
                ui.get("visibility")
                if isinstance(ui, dict)
                else None
            )
            if isinstance(mention, dict) and isinstance(
                visibility,
                list,
            ) and "app" in visibility:
                if tool.get("name"):
                    names.append(str(tool["name"]))
        return bool(names), [f"tool:{name}" for name in sorted(names)]

    entrypoint_type = {
        "sidebar_app": "global",
        "conversation_panel": "thread",
        "file_viewer_editor": "file",
    }.get(extension_id)
    if entrypoint_type:
        matches = []
        for tool in tools:
            meta = _tool_meta(tool)
            openai_ui = meta.get("openai/ui")
            entrypoints = (
                openai_ui.get("entrypoints")
                if isinstance(openai_ui, dict)
                else None
            )
            if not isinstance(entrypoints, list):
                continue
            for entrypoint in entrypoints:
                if not isinstance(entrypoint, dict):
                    continue
                if entrypoint.get("type") != entrypoint_type:
                    continue
                if entrypoint_type == "file":
                    extensions = entrypoint.get("extensions")
                    if not isinstance(extensions, list) or not extensions:
                        continue
                uri = _tool_resource_uri(tool)
                observation = resources.get(uri or "")
                if not uri or not observation or not observation.get("mcp_app"):
                    continue
                matches.append(str(tool.get("name") or uri))
        return bool(matches), [
            f"entrypoint:{entrypoint_type}:{name}"
            for name in sorted(matches)
        ]

    if extension_id == "display_modes":
        matching = []
        for uri, observation in resources.items():
            ui_meta = observation.get("openai_ui")
            if not isinstance(ui_meta, dict):
                continue
            if (
                isinstance(ui_meta.get("availableDisplayModes"), list)
                or isinstance(ui_meta.get("preferredDisplayMode"), str)
            ):
                matching.append(uri)
        return bool(matching), [
            f"resource:{uri}" for uri in sorted(matching)
        ]

    return False, []


def _settings_capability(discover: dict[str, Any]) -> dict[str, Any] | None:
    capabilities = discover.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    extensions = capabilities.get("extensions")
    if isinstance(extensions, dict):
        value = extensions.get("openai/settings")
        if isinstance(value, dict):
            return value
    experimental = capabilities.get("experimental")
    if isinstance(experimental, dict):
        value = experimental.get("openai/settings")
        if isinstance(value, dict):
            return value
    return None


def _tool_meta(tool: dict[str, Any]) -> dict[str, Any]:
    meta = tool.get("_meta")
    return meta if isinstance(meta, dict) else {}


def _tool_resource_uri(tool: dict[str, Any]) -> str | None:
    meta = _tool_meta(tool)
    ui = meta.get("ui")
    if isinstance(ui, dict):
        value = ui.get("resourceUri")
        if isinstance(value, str) and value:
            return value
    return None


def _resource_observation(
    uri: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    contents = result.get("contents")
    if not isinstance(contents, list):
        return {
            "ok": False,
            "mcp_app": False,
            "mime_types": [],
            "openai_ui": {},
            "content_count": 0,
            "content_sha256": None,
        }
    mime_types = []
    openai_ui: dict[str, Any] = {}
    mcp_app = False
    fingerprint_items: list[dict[str, Any]] = []
    for item in contents:
        if not isinstance(item, dict):
            continue
        mime = item.get("mimeType")
        if isinstance(mime, str):
            mime_types.append(mime)
            if mime == "text/html;profile=mcp-app":
                mcp_app = True
        meta = item.get("_meta")
        if isinstance(meta, dict):
            candidate = meta.get("openai/ui")
            if isinstance(candidate, dict):
                openai_ui.update(candidate)
        fingerprint_items.append(
            {
                "uri": item.get("uri"),
                "mimeType": mime,
                "text": item.get("text"),
                "blob": item.get("blob"),
                "openai_ui": (
                    meta.get("openai/ui")
                    if isinstance(meta, dict)
                    and isinstance(meta.get("openai/ui"), dict)
                    else {}
                ),
            }
        )
    return {
        "ok": True,
        "mcp_app": mcp_app,
        "mime_types": sorted(set(mime_types)),
        "openai_ui": openai_ui,
        "content_count": len(fingerprint_items),
        "content_sha256": _json_sha256(fingerprint_items),
    }


def _tool_observation(
    tool: dict[str, Any],
) -> dict[str, Any]:
    meta = _tool_meta(tool)
    safe_meta: dict[str, Any] = {}
    for key in (
        "ui",
        "openai/ui",
        "openai/extensions",
        "openai/toolInvocation",
        "securitySchemes",
    ):
        value = meta.get(key)
        if value is not None:
            safe_meta[key] = value
    observation: dict[str, Any] = {
        "name": tool.get("name"),
        "title": tool.get("title"),
        "description": tool.get("description"),
        "inputSchema": tool.get("inputSchema"),
        "outputSchema": tool.get("outputSchema"),
        "annotations": tool.get("annotations"),
        "securitySchemes": tool.get("securitySchemes"),
        "_meta": safe_meta,
    }
    return {
        key: value
        for key, value in observation.items()
        if value is not None
    }


def _runtime_fingerprint(
    *,
    protocol_version: str,
    era: str,
    discover: dict[str, Any],
    tools: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    capabilities = discover.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    protocol_payload = {
        "version": protocol_version,
        "era": era,
    }
    components = {
        "protocol_sha256": _json_sha256(protocol_payload),
        "capabilities_sha256": _json_sha256(capabilities),
        "tools_sha256": _json_sha256(tools),
        "resources_sha256": _json_sha256(resources),
    }
    surface = {
        "protocol": protocol_payload,
        "capabilities": capabilities,
        "tools": tools,
        "resources": resources,
    }
    return {
        "schema_version": "0.1",
        "sha256": _json_sha256(surface),
        "components": components,
        "counts": {
            "tools": len(tools),
            "resources": len(resources),
        },
    }


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _server_info(
    discover: dict[str, Any],
    era: str,
) -> dict[str, Any]:
    if era == "legacy":
        info = discover.get("serverInfo")
        return info if isinstance(info, dict) else {}
    meta = discover.get("_meta")
    if isinstance(meta, dict):
        info = meta.get("io.modelcontextprotocol/serverInfo")
        if isinstance(info, dict):
            return info
    return {}


def _modern_meta() -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL,
        "io.modelcontextprotocol/clientInfo": {
            "name": "mado-plugin-factory",
            "version": "0.9.0",
        },
        "io.modelcontextprotocol/clientCapabilities": {
            "extensions": {
                "openai/elicitation": {
                    "form": {}
                }
            }
        },
    }


def _parse_http_message(
    body: str,
    content_type: str,
    request_id: int,
) -> dict[str, Any]:
    if "text/event-stream" in content_type:
        candidates = []
        for line in body.splitlines():
            if line.startswith("data:"):
                candidates.append(line[5:].strip())
        for item in candidates:
            try:
                value = json.loads(item)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("id") == request_id:
                return value
        raise RuntimeSmokeError(
            "MCP HTTP response did not contain the expected JSON-RPC event"
        )
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeSmokeError(
            "MCP HTTP response was not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeSmokeError("MCP HTTP response must be a JSON object")
    return value


def _rpc_error_text(message: dict[str, Any]) -> str:
    error = message.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        text = error.get("message")
        return f"{code}: {text}"
    return "unknown JSON-RPC error"


def _smoke_id(
    server_name: str,
    protocol: str,
    expected: list[str],
    tool_names: list[str],
    resource_uris: list[str],
) -> str:
    payload = {
        "server": server_name,
        "protocol": protocol,
        "expected": expected,
        "tools": tool_names,
        "resources": resource_uris,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]


def _warnings(
    *,
    expected: list[str],
    host_required: list[str],
    transport: str,
    mode: str,
) -> list[str]:
    warnings = [
        "Runtime verification in M0.9 covers MCP server protocol evidence, not a full ChatGPT UI interaction."
    ]
    if host_required:
        warnings.append(
            "Some detected extensions require ChatGPT host or MCP App interaction and remain host_required: "
            + ", ".join(host_required)
        )
    if transport == "streamable-http" and mode == "auto":
        warnings.append(
            "M0.9 probes streamable HTTP using the modern MCP 2026-07-28 stateless protocol."
        )
    if not expected:
        warnings.append(
            "No statically detected extension surfaces were available to verify."
        )
    return warnings


def _write_evidence(
    root: Path,
    report: dict[str, Any],
    *,
    output: str,
    force: bool,
) -> str:
    target = _safe_relative(
        root,
        output,
        label="runtime evidence output",
    )
    _reject_symlink_target(root, target)
    rendered = (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current != rendered and not force:
            raise RuntimeSmokeError(
                f"runtime evidence differs at {target}; use --force to replace it"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != rendered:
        target.write_text(rendered, encoding="utf-8")
    return target.relative_to(root).as_posix()


def _safe_relative(root: Path, value: str, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeSmokeError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeSmokeError(f"{label} must stay inside the plugin root")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RuntimeSmokeError(f"{label} must stay inside the plugin root") from exc
    return target


def _reject_symlink_target(root: Path, target: Path) -> None:
    rel = target.relative_to(root)
    current = root
    for part in rel.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RuntimeSmokeError(
                f"refusing symlinked runtime evidence target: {current}"
            )
