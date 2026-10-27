from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from irbg.engine.provider import OpenRouterClient
from irbg.engine.types import ChatMessage

CLAUDE_BIN = shutil.which("claude", path="/opt/homebrew/bin") or "claude"
CODEX_BIN = shutil.which("codex") or "codex"
TURN_TIMEOUT_S = 420
RETRY_BACKOFF_S = (20, 90, 300)


class BackendError(Exception):
    """Raised when a model call fails after all retries."""


@dataclass(frozen=True)
class TurnReply:
    text: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class Session(Protocol):
    def send(self, user_text: str) -> TurnReply:
        """Send one user turn and return the model reply."""
        ...

    def close(self) -> None:
        """Release any resources held by the session."""
        ...


def _with_retries(fn, what: str):
    """Call fn, retrying with backoff; raise BackendError at the end."""
    last: Exception | None = None
    for wait in (0, *RETRY_BACKOFF_S):
        if wait:
            time.sleep(wait)
        try:
            return fn()
        except (BackendError, subprocess.TimeoutExpired, OSError) as exc:
            last = exc
    raise BackendError(f"{what} failed after retries: {last}")


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a CLI with no stdin, inside cwd, with a turn timeout."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=TURN_TIMEOUT_S,
    )


@dataclass
class OpenRouterSession:
    client: OpenRouterClient
    model_id: str
    system: str
    max_tokens: int
    temperature: float
    price_input: float
    price_output: float
    messages: list[ChatMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages = [ChatMessage(role="system", content=self.system)]

    def send(self, user_text: str) -> TurnReply:
        """Send the full message history plus one user turn."""
        self.messages.append(ChatMessage(role="user", content=user_text))

        def call() -> TurnReply:
            r = self.client.chat_messages(
                model_id=self.model_id,
                messages=self.messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            if not r.success or not r.text.strip():
                raise BackendError(r.error or "empty response")
            cost = r.cost_usd
            if cost is None:
                cost = (
                    r.input_tokens * self.price_input
                    + r.output_tokens * self.price_output
                ) / 1_000_000
            return TurnReply(
                text=r.text,
                latency_ms=r.latency_ms,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                cost_usd=cost,
            )

        reply = _with_retries(call, f"openrouter {self.model_id}")
        self.messages.append(ChatMessage(role="assistant", content=reply.text))
        return reply

    def close(self) -> None:
        """Nothing to release; the client is shared."""


@dataclass
class CodexSession:
    model_id: str
    system: str
    output_schema: Path | None = None
    thread_id: str | None = None

    def __post_init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="govbench-codex-"))
        self.sys_file = self.dir / "instructions.txt"
        self.sys_file.write_text(self.system)

    def send(self, user_text: str) -> TurnReply:
        """Start a Codex thread or resume it with one more turn."""
        last = self.dir / "last.txt"
        flags = [
            "-m",
            self.model_id,
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "-c",
            f"model_instructions_file={self.sys_file}",
            "-o",
            str(last),
            "--json",
        ]
        if self.output_schema is not None:
            flags += ["--output-schema", str(self.output_schema)]

        def call() -> TurnReply:
            last.unlink(missing_ok=True)
            if self.thread_id:
                cmd = [CODEX_BIN, "exec", "resume", *flags, self.thread_id]
            else:
                cmd = [CODEX_BIN, "exec", "-s", "read-only", *flags]
            started = time.perf_counter()
            out = _run([*cmd, user_text], self.dir)
            latency = int((time.perf_counter() - started) * 1000)
            thread, usage = self.thread_id, {}
            for line in out.stdout.splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                thread = ev.get("thread_id", thread)
                if isinstance(ev.get("usage"), dict):
                    usage = ev["usage"]
            text = last.read_text() if last.exists() else ""
            if out.returncode != 0 or not text.strip():
                raise BackendError(
                    f"codex rc={out.returncode}: {out.stderr[-400:]}"
                )
            self.thread_id = thread
            return TurnReply(
                text=text,
                latency_ms=latency,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )

        return _with_retries(call, f"codex {self.model_id}")

    def close(self) -> None:
        """Remove the session's scratch directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


@dataclass
class ClaudeCodeSession:
    model_id: str
    system: str
    session_id: str | None = None

    def __post_init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="govbench-claude-"))

    def send(self, user_text: str) -> TurnReply:
        """Start a Claude Code session or resume it with one more turn."""
        cmd = [
            CLAUDE_BIN,
            "-p",
            "--model",
            self.model_id,
            "--system-prompt",
            self.system,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--output-format",
            "json",
        ]
        if self.session_id:
            cmd += ["--resume", self.session_id]

        def call() -> TurnReply:
            started = time.perf_counter()
            out = _run([*cmd, user_text], self.dir)
            latency = int((time.perf_counter() - started) * 1000)
            try:
                d = json.loads(out.stdout)
            except json.JSONDecodeError as exc:
                raise BackendError(
                    f"claude rc={out.returncode}: {out.stderr[-400:]}"
                ) from exc
            text = str(d.get("result") or "")
            if d.get("is_error") or not text.strip():
                raise BackendError(f"claude error: {text[:400]}")
            self.session_id = d.get("session_id", self.session_id)
            usage = d.get("usage") or {}
            return TurnReply(
                text=text,
                latency_ms=latency,
                input_tokens=int(usage.get("input_tokens", 0))
                + int(usage.get("cache_read_input_tokens", 0))
                + int(usage.get("cache_creation_input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )

        return _with_retries(call, f"claude {self.model_id}")

    def close(self) -> None:
        """Remove the session's scratch directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


def openrouter_client_from_env() -> OpenRouterClient:
    """Build an OpenRouter client from OPENROUTER_API_KEY."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise BackendError("OPENROUTER_API_KEY is not set")
    return OpenRouterClient(key, timeout=300.0, app_name="GovBench")


def cli_versions() -> dict[str, str]:
    """Versions of the subscription CLIs, for the run manifest."""
    versions: dict[str, str] = {}
    for name, binary in (("codex", CODEX_BIN), ("claude", CLAUDE_BIN)):
        try:
            out = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
            versions[name] = out.stdout.strip() or out.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            versions[name] = f"unavailable: {exc}"
    return versions
