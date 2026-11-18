"""Live end-to-end verification script that sends a harmless sample sentence through the connected browser extension on https://cleverhumanizer.ai."""
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from desktop_app.config import load_config, sync_extension_config
from desktop_app.ws_server import LocalBridgeServer


async def main() -> int:
    cfg = load_config()
    sync_extension_config(cfg)

    server = LocalBridgeServer(
        host="127.0.0.1",
        port=int(cfg["port"]),
        auth_token=str(cfg["auth_token"]),
        on_progress=lambda req_id, st, pct: print(f"[Progress {pct}%] {st}", flush=True),
    )
    await server.start()
    print(
        f"Listening on 127.0.0.1:{server.port} — waiting for browser extension to connect...",
        flush=True,
    )

    try:
        for _ in range(120):
            if server.has_connected_extension:
                break
            await asyncio.sleep(0.5)

        if not server.has_connected_extension:
            print("ERROR: Browser extension did not connect within 60 seconds.", flush=True)
            return 1

        print("Extension connected! Sending harmless sample sentence to https://cleverhumanizer.ai...", flush=True)
        sample = (
            "The primary reasons for these task failures were account or login problems (25.3%), "
            "administrative restrictions or holds (20.2%), internet or electricity interruptions "
            "(18.3%), unclear reasons where the portal gave no explanation (15.8%), and server "
            "crashes or freezes during busy times (8.5%)."
        )
        res = await server.request_humanize(sample, timeout_sec=120.0)
        print("Result payload:", res, flush=True)
        if res.get("type") == "HUMANIZE_RESULT" and res.get("text", "").strip():
            print("LIVE E2E CHECK PASSED!", flush=True)
            return 0
        print("LIVE E2E CHECK FAILED:", res, flush=True)
        return 1
    finally:
        await server.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

