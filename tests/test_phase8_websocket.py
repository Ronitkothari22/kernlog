from __future__ import annotations

import asyncio
import unittest

from app.routers.monitoring import WsBridgeManager


class DummyWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class Phase8WebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_sends_to_all_clients(self) -> None:
        manager = WsBridgeManager()
        ws1 = DummyWebSocket()
        ws2 = DummyWebSocket()
        key = "t1:h1"
        manager._clients[key] = {ws1, ws2}

        await manager._broadcast(key, [{"type": "metric", "value": 10}])

        self.assertEqual(ws1.sent, [{"type": "metric", "value": 10}])
        self.assertEqual(ws2.sent, [{"type": "metric", "value": 10}])

    async def test_register_unregister_lifecycle(self) -> None:
        manager = WsBridgeManager()

        async def fake_relay(_tenant_id: str, _host_id: str) -> None:
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                return

        manager._relay_loop = fake_relay  # type: ignore[method-assign]

        ws = DummyWebSocket()
        await manager.register("t1", "h1", ws)
        self.assertIn("t1:h1", manager._clients)
        self.assertIn("t1:h1", manager._tasks)

        await manager.unregister("t1", "h1", ws)
        self.assertNotIn("t1:h1", manager._clients)
        self.assertNotIn("t1:h1", manager._tasks)


if __name__ == "__main__":
    unittest.main()
