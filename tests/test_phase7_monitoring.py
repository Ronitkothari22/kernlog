from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fastapi import HTTPException

from app.routers.monitoring import _decode_cursor, _encode_cursor


class Phase7MonitoringTests(unittest.TestCase):
    def test_cursor_roundtrip(self) -> None:
        ts = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
        cursor = _encode_cursor(ts, 99)
        decoded_ts, decoded_id = _decode_cursor(cursor)
        self.assertEqual(decoded_ts, ts)
        self.assertEqual(decoded_id, 99)

    def test_cursor_rejects_invalid_payload(self) -> None:
        with self.assertRaises(HTTPException):
            _decode_cursor("bad-cursor")


if __name__ == "__main__":
    unittest.main()
