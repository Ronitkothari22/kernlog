from __future__ import annotations

import unittest

from app.ingestion import IngestionError, infer_severity, parse_ingest_message


class Phase6IngestionTests(unittest.TestCase):
    def test_parse_rejects_malformed_json(self) -> None:
        with self.assertRaises(IngestionError):
            parse_ingest_message("metrics.system", b"{not-json", "m1")

    def test_parse_requires_tenant_id(self) -> None:
        with self.assertRaises(IngestionError):
            parse_ingest_message("metrics.system", b'{"host_id":"h1"}', "m2")

    def test_parse_accepts_valid_payload(self) -> None:
        msg = parse_ingest_message(
            "metrics.system",
            b'{"tenant_id":"t1","host_id":"h1","metric_name":"cpu","metric_value":10}',
            "m3",
        )
        self.assertEqual(msg.topic, "metrics.system")
        self.assertEqual(msg.payload["tenant_id"], "t1")

    def test_severity_inference(self) -> None:
        self.assertEqual(infer_severity("2026 ERROR disk full"), "ERROR")
        self.assertEqual(infer_severity("boot complete"), "INFO")


if __name__ == "__main__":
    unittest.main()
