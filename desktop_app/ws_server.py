"""Localhost-only RFC 6455 WebSocket server with shared-secret token authentication."""
import asyncio
import base64
import hashlib
import hmac
import json
import struct
import time
import urllib.parse
import uuid
from typing import Any, Callable, Dict, Optional, Set

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketClient:
    """Represents a single authenticated WebSocket client connection."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer: str,
    ):
        self.reader = reader
        self.writer = writer
        self.peer = peer
        self.connected = True
        self.last_seen = time.time()
        self._write_lock = asyncio.Lock()

    async def send_json(self, payload: Dict[str, Any]) -> bool:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return await self.send_frame(0x1, data)

    async def send_frame(self, opcode: int, payload: bytes = b"") -> bool:
        if not self.connected:
            return False
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))

        try:
            async with self._write_lock:
                self.writer.write(bytes(header) + payload)
                await self.writer.drain()
            return True
        except Exception:
            self.connected = False
            return False

    async def close(self) -> None:
        if not self.connected:
            return
        try:
            await self.send_frame(0x8, b"")
        except Exception:
            pass
        self.connected = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


class LocalBridgeServer:
    """
    WebSocket bridge server on 127.0.0.1:<port> with shared-secret authentication,
    heartbeat monitoring, and request/response tracking.
    """

    def __init__(
        self,
        host: str,
        port: int,
        auth_token: str,
        on_progress: Optional[Callable[[str, str, int], None]] = None,
        on_result: Optional[Callable[[str, str, int], None]] = None,
        on_error: Optional[Callable[[str, str, str], None]] = None,
        on_connection_change: Optional[Callable[[bool], None]] = None,
    ):
        if host != "127.0.0.1":
            raise ValueError("Server must bind strictly to 127.0.0.1")
        self.host = "127.0.0.1"
        self.port = int(port)
        self.auth_token = auth_token
        self.on_progress = on_progress
        self.on_result = on_result
        self.on_error = on_error
        self.on_connection_change = on_connection_change

        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: Set[WebSocketClient] = set()
        self._active_request_id: Optional[str] = None
        self._pending_futures: Dict[str, asyncio.Future] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def has_connected_extension(self) -> bool:
        return any(c.connected for c in self._clients)

    @property
    def is_busy(self) -> bool:
        return self._active_request_id is not None

    def verify_token(self, candidate: Optional[str]) -> bool:
        if not candidate or not self.auth_token:
            return False
        return hmac.compare_digest(str(candidate), str(self.auth_token))

    async def start(self) -> None:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((self.host, self.port))
        sock.listen(16)
        sock.setblocking(False)
        self._server = await asyncio.start_server(
            self._handle_connection, sock=sock
        )
        sockets = self._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        for client in list(self._clients):
            await client.close()
        self._clients.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(15.0)
            now = time.time()
            dead = []
            for client in list(self._clients):
                if not client.connected or (now - client.last_seen > 65.0):
                    dead.append(client)
                else:
                    ok = await client.send_json(
                        {"type": "PING", "timestamp": int(now * 1000)}
                    )
                    if not ok:
                        dead.append(client)
            for client in dead:
                await self._remove_client(client)

    async def _remove_client(self, client: WebSocketClient) -> None:
        was_connected = self.has_connected_extension
        self._clients.discard(client)
        await client.close()
        now_connected = self.has_connected_extension
        if was_connected and not now_connected:
            if self.on_connection_change:
                self.on_connection_change(False)
            # Fail any active request immediately if all extension clients disconnected
            if self._active_request_id:
                req_id = self._active_request_id
                self._active_request_id = None
                err = {
                    "type": "HUMANIZE_ERROR",
                    "requestId": req_id,
                    "code": "EXTENSION_DISCONNECTED",
                    "message": "Browser extension disconnected while humanizing. Is your browser still open?",
                }
                fut = self._pending_futures.pop(req_id, None)
                if fut and not fut.done():
                    fut.set_result(err)
                if self.on_error:
                    self.on_error(req_id, err["code"], err["message"])

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peername = writer.get_extra_info("peername")
        peer_ip = peername[0] if peername else ""
        if peer_ip != "127.0.0.1":
            writer.close()
            return

        try:
            raw_headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
        except Exception:
            writer.close()
            return

        header_text = raw_headers.decode("latin-1", errors="replace")
        lines = header_text.split("\r\n")
        if not lines or " " not in lines[0]:
            writer.close()
            return

        method, path, _ = lines[0].split(" ", 2)
        headers: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        parsed_url = urllib.parse.urlparse(path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        token_param = query_params.get("token", [None])[0]
        header_token = headers.get("x-auth-token")
        candidate_token = token_param or header_token

        if not self.verify_token(candidate_token):
            resp = (
                "HTTP/1.1 403 Forbidden\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 23\r\n"
                "Connection: close\r\n\r\n"
                "403 Invalid Auth Token\n"
            )
            writer.write(resp.encode("ascii"))
            await writer.drain()
            writer.close()
            return

        if headers.get("upgrade", "").lower() != "websocket":
            # Health check endpoint for authorized local diagnostics
            if method == "GET" and parsed_url.path == "/health":
                body = json.dumps(
                    {
                        "ok": True,
                        "extensionConnected": self.has_connected_extension,
                        "busy": self.is_busy,
                    }
                ).encode("utf-8")
                resp = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii") + body
                writer.write(resp)
                await writer.drain()
            writer.close()
            return

        ws_key = headers.get("sec-websocket-key", "")
        if not ws_key:
            writer.close()
            return

        accept_val = base64.b64encode(
            hashlib.sha1((ws_key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        handshake = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_val}\r\n\r\n"
        )
        writer.write(handshake.encode("ascii"))
        await writer.drain()

        client = WebSocketClient(reader, writer, peer=f"{peer_ip}:{peername[1]}")
        was_connected = self.has_connected_extension
        self._clients.add(client)
        if not was_connected and self.on_connection_change:
            self.on_connection_change(True)

        await client.send_json({"type": "WELCOME", "serverVersion": "1.0.0"})

        try:
            while client.connected:
                frame = await self._read_frame(reader)
                if frame is None:
                    break
                opcode, payload = frame
                client.last_seen = time.time()
                if opcode == 0x8:  # Close
                    break
                elif opcode == 0x9:  # Ping
                    await client.send_frame(0xA, payload)
                elif opcode == 0xA:  # Pong
                    continue
                elif opcode == 0x1:  # Text
                    try:
                        msg = json.loads(payload.decode("utf-8"))
                    except Exception:
                        await client.send_json(
                            {
                                "type": "ERROR",
                                "code": "BAD_JSON",
                                "message": "Malformed JSON frame",
                            }
                        )
                        continue
                    await self._handle_client_message(client, msg)
        except Exception:
            pass
        finally:
            await self._remove_client(client)

    async def _read_frame(
        self, reader: asyncio.StreamReader
    ) -> Optional[tuple[int, bytes]]:
        try:
            first_two = await reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionError):
            return None

        b1, b2 = first_two[0], first_two[1]
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F

        try:
            if length == 126:
                ext = await reader.readexactly(2)
                length = struct.unpack("!H", ext)[0]
            elif length == 127:
                ext = await reader.readexactly(8)
                length = struct.unpack("!Q", ext)[0]

            if length > 10 * 1024 * 1024:  # 10 MB sanity cap
                return None

            mask_key = await reader.readexactly(4) if masked else b""
            payload = await reader.readexactly(length) if length > 0 else b""
        except (asyncio.IncompleteReadError, ConnectionError):
            return None

        if masked and payload:
            unmasked = bytearray(length)
            for i in range(length):
                unmasked[i] = payload[i] ^ mask_key[i % 4]
            payload = bytes(unmasked)

        return opcode, payload

    async def _handle_client_message(
        self, client: WebSocketClient, msg: Dict[str, Any]
    ) -> None:
        # Every client message must either come over the already-authenticated socket
        # and if it carries a token field, it must match.
        if "token" in msg and not self.verify_token(msg.get("token")):
            await client.send_json(
                {
                    "type": "ERROR",
                    "code": "AUTH_FAILED",
                    "message": "Invalid authentication token",
                }
            )
            await client.close()
            return

        msg_type = msg.get("type", "")
        if msg_type in ("HELLO", "HEARTBEAT", "PING"):
            await client.send_json(
                {"type": "PONG", "timestamp": int(time.time() * 1000)}
            )
            return

        if msg_type == "PONG":
            return

        req_id = msg.get("requestId")
        if msg_type == "HUMANIZE_PROGRESS":
            status = str(msg.get("status", "Humanizing…"))
            percent = int(msg.get("percent", 0))
            if self.on_progress and req_id:
                self.on_progress(req_id, status, percent)
            return

        if msg_type == "HUMANIZE_RESULT":
            text = str(msg.get("text", ""))
            words = int(msg.get("words", len(text.split())))
            if req_id == self._active_request_id:
                self._active_request_id = None
            fut = self._pending_futures.pop(req_id, None) if req_id else None
            if fut and not fut.done():
                fut.set_result(msg)
            if self.on_result and req_id:
                self.on_result(req_id, text, words)
            return

        if msg_type == "HUMANIZE_ERROR":
            code = str(msg.get("code", "UNKNOWN_ERROR"))
            err_message = str(msg.get("message", "Unknown Clever AI error"))
            if req_id == self._active_request_id:
                self._active_request_id = None
            fut = self._pending_futures.pop(req_id, None) if req_id else None
            if fut and not fut.done():
                fut.set_result(msg)
            if self.on_error and req_id:
                self.on_error(req_id, code, err_message)
            return

    async def request_humanize(
        self, text: str, timeout_sec: float = 180.0
    ) -> Dict[str, Any]:
        """
        Send a HUMANIZE_REQUEST to the connected browser extension and await the result.
        Never fails silently; returns structured dict with 'type' == 'HUMANIZE_RESULT' or 'HUMANIZE_ERROR'.
        """
        if not text or not text.strip():
            return {
                "type": "HUMANIZE_ERROR",
                "requestId": "",
                "code": "EMPTY_TEXT",
                "message": "Clipboard text is empty. Please copy some text in Word first.",
            }

        if self._active_request_id is not None:
            return {
                "type": "HUMANIZE_ERROR",
                "requestId": self._active_request_id,
                "code": "BUSY",
                "message": "A humanize request is already running. Please wait for it to finish.",
            }

        active_clients = [c for c in self._clients if c.connected]
        if not active_clients:
            return {
                "type": "HUMANIZE_ERROR",
                "requestId": "",
                "code": "EXTENSION_DISCONNECTED",
                "message": "Browser extension is not connected. Make sure your browser is open and the Humanize Helper extension is enabled.",
            }

        req_id = uuid.uuid4().hex
        self._active_request_id = req_id
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_futures[req_id] = fut

        payload = {
            "type": "HUMANIZE_REQUEST",
            "requestId": req_id,
            "text": text,
            "token": self.auth_token,
            "timestamp": int(time.time() * 1000),
        }

        sent = False
        for client in reversed(active_clients):
            if await client.send_json(payload):
                sent = True
                break

        if not sent:
            self._active_request_id = None
            self._pending_futures.pop(req_id, None)
            return {
                "type": "HUMANIZE_ERROR",
                "requestId": req_id,
                "code": "EXTENSION_SEND_FAILED",
                "message": "Failed to send text to browser extension. Please check that your browser is open.",
            }

        try:
            result = await asyncio.wait_for(fut, timeout=timeout_sec)
            return result
        except asyncio.TimeoutError:
            if self._active_request_id == req_id:
                self._active_request_id = None
            self._pending_futures.pop(req_id, None)
            err = {
                "type": "HUMANIZE_ERROR",
                "requestId": req_id,
                "code": "TIMEOUT",
                "message": f"Clever AI timed out after {int(timeout_sec)} seconds. Check the Clever AI tab or your internet connection.",
            }
            if self.on_error:
                self.on_error(req_id, err["code"], err["message"])
            return err

