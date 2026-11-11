"""Mantém os bots do CyberCloud online no Discord (Gateway).

Uploads continuam na API REST (`discord_storage`). Esta sessão só faz IDENTIFY
e heartbeat para o bot aparecer ativo. Roda em processo único (systemd),
não no uvicorn — dois workers brigariam pela mesma sessão.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import signal
import sys
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import get_settings

logger = logging.getLogger("discord_gateway")

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
IDENTIFY_OP = 2
RESUME_OP = 6
HEARTBEAT_OP = 1
HELLO_OP = 10
HEARTBEAT_ACK_OP = 11
RECONNECT_OP = 7
INVALID_SESSION_OP = 9
DISPATCH_OP = 0

# GUILDS — não privilegiado; suficiente para ficar online.
GATEWAY_INTENTS = 1 << 0

FATAL_CLOSE_CODES = {4004, 4010, 4011, 4013, 4014}
MAX_BACKOFF_SECONDS = 60.0


def identify_payload(token: str) -> dict[str, Any]:
    return {
        "op": IDENTIFY_OP,
        "d": {
            "token": token,
            "intents": GATEWAY_INTENTS,
            "properties": {
                "os": sys.platform,
                "browser": "cyberhost",
                "device": "cyberhost",
            },
        },
    }


def resume_payload(token: str, session_id: str, seq: int | None) -> dict[str, Any]:
    return {
        "op": RESUME_OP,
        "d": {"token": token, "session_id": session_id, "seq": seq},
    }


def heartbeat_payload(seq: int | None) -> dict[str, Any]:
    return {"op": HEARTBEAT_OP, "d": seq}


def hello_interval_ms(message: dict[str, Any]) -> int:
    data = message.get("d") or {}
    interval = data.get("heartbeat_interval")
    if not isinstance(interval, int) or interval < 1000:
        raise ValueError("HELLO sem heartbeat_interval válido")
    return interval


class BotGateway:
    def __init__(self, index: int, token: str):
        self.index = index
        self._token = token
        self.seq: int | None = None
        self.session_id: str | None = None
        self.username: str | None = None
        self._stop = asyncio.Event()
        self._ack = asyncio.Event()
        self._ack.set()

    @property
    def label(self) -> str:
        name = self.username or "?"
        return f"bot #{self.index + 1} ({name})"

    def request_stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                await self._connect()
                backoff = 2.0
            except asyncio.CancelledError:
                raise
            except _FatalGateway as exc:
                logger.error("[Discord] %s sessão encerrada: %s", self.label, exc)
                return
            except Exception as exc:
                logger.warning("[Discord] %s desconectou: %s", self.label, exc)
            if self._stop.is_set():
                return
            jitter = random.uniform(0, 1.5)
            await asyncio.sleep(min(backoff, MAX_BACKOFF_SECONDS) + jitter)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _connect(self) -> None:
        try:
            async with websockets.connect(
                GATEWAY_URL,
                max_size=2 * 1024 * 1024,
                ping_interval=None,
                close_timeout=5,
            ) as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                hello = json.loads(raw)
                if hello.get("op") != HELLO_OP:
                    raise RuntimeError(f"esperado HELLO, veio op={hello.get('op')}")
                interval_ms = hello_interval_ms(hello)
                heartbeats = asyncio.create_task(self._heartbeat_loop(ws, interval_ms))
                try:
                    if self.session_id and self.seq is not None:
                        await ws.send(json.dumps(resume_payload(self._token, self.session_id, self.seq)))
                    else:
                        await ws.send(json.dumps(identify_payload(self._token)))
                    await self._event_loop(ws)
                finally:
                    heartbeats.cancel()
                    try:
                        await heartbeats
                    except asyncio.CancelledError:
                        pass
        except ConnectionClosed as exc:
            if exc.code in FATAL_CLOSE_CODES:
                raise _FatalGateway(f"close {exc.code}") from exc
            raise

    async def _heartbeat_loop(self, ws: Any, interval_ms: int) -> None:
        delay = (interval_ms / 1000) * random.uniform(0.1, 0.5)
        try:
            await asyncio.sleep(delay)
            while not self._stop.is_set():
                if not self._ack.is_set():
                    await ws.close(4000, "heartbeat ack timeout")
                    return
                self._ack.clear()
                await ws.send(json.dumps(heartbeat_payload(self.seq)))
                await asyncio.sleep(interval_ms / 1000)
        except (ConnectionClosed, asyncio.CancelledError):
            return

    async def _event_loop(self, ws: Any) -> None:
        async for raw in ws:
            if self._stop.is_set():
                return
            message = json.loads(raw)
            op = message.get("op")
            if message.get("s") is not None:
                self.seq = message["s"]

            if op == HEARTBEAT_ACK_OP:
                self._ack.set()
            elif op == HEARTBEAT_OP:
                await ws.send(json.dumps(heartbeat_payload(self.seq)))
            elif op == RECONNECT_OP:
                return
            elif op == INVALID_SESSION_OP:
                resumable = bool(message.get("d"))
                if not resumable:
                    self.session_id = None
                    self.seq = None
                await asyncio.sleep(random.uniform(1, 5))
                return
            elif op == DISPATCH_OP:
                self._on_dispatch(message)

    def _on_dispatch(self, message: dict[str, Any]) -> None:
        event = message.get("t")
        data = message.get("d") or {}
        if event == "READY":
            user = data.get("user") or {}
            self.username = user.get("username")
            self.session_id = data.get("session_id")
            logger.info("[Discord] %s online", self.label)
        elif event == "RESUMED":
            logger.info("[Discord] %s sessão retomada", self.label)


class _FatalGateway(Exception):
    pass


async def _run_bot(index: int, token: str, stagger: float) -> None:
    await asyncio.sleep(stagger)
    await BotGateway(index, token).run_forever()


async def run_gateways(tokens: list[str]) -> None:
    if not tokens:
        logger.warning("[Discord] Nenhum token — gateway em espera")
        await asyncio.Event().wait()
        return

    logger.info("[Discord] Gateway iniciando %s bot(s)", len(tokens))
    tasks = [
        asyncio.create_task(_run_bot(index, token, index * 0.4), name=f"discord-bot-{index + 1}")
        for index, token in enumerate(tokens)
    ]
    stop = asyncio.Event()

    def _signal(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop.set())

    try:
        await stop.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    settings = get_settings()
    tokens = settings.discord_bot_token_list
    try:
        asyncio.run(run_gateways(tokens))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
