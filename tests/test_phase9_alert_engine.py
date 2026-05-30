from __future__ import annotations

import unittest

from alert_engine.main import AlertEvaluator, AlertRule, MetricEvent, RuleCache, _parse_metric_event


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.published: list[tuple[str, dict]] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, _ttl_seconds: int, value: str) -> None:
        self.store[key] = value

    def publish(self, channel: str, payload: dict) -> None:
        self.published.append((channel, payload))


class FakeRuleCache:
    def __init__(self, rules: list[AlertRule]) -> None:
        self.rules = rules

    def get_rules(self, _tenant_id: str, _host_id: str, _metric_name: str) -> list[AlertRule]:
        return self.rules


class Phase9AlertEngineTests(unittest.TestCase):
    def test_parse_metric_event(self) -> None:
        event = _parse_metric_event(
            {
                "tenant_id": "t1",
                "host_id": "h1",
                "metric_name": "cpu",
                "metric_value": 95,
                "ts": "2026-05-30T12:00:00Z",
            }
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.metric_value, 95.0)

    def test_breach_streak_triggers_fire_after_consecutive(self) -> None:
        redis_client = FakeRedis()
        rule = AlertRule(
            id="r1",
            tenant_id="t1",
            name="CPU High",
            metric_name="cpu",
            operator="gt",
            threshold=90,
            severity="critical",
            host_id="h1",
            consecutive=2,
            enabled=True,
        )
        evaluator = AlertEvaluator(redis_client=redis_client, rule_cache=FakeRuleCache([rule]))

        fired: list[tuple[MetricEvent, AlertRule]] = []
        evaluator._fire_if_not_open = lambda event, active_rule: fired.append((event, active_rule))  # type: ignore[method-assign]
        evaluator._resolve_if_open = lambda event, active_rule: None  # type: ignore[method-assign]

        e1 = MetricEvent(tenant_id="t1", host_id="h1", metric_name="cpu", metric_value=91, ts=event_ts())
        e2 = MetricEvent(tenant_id="t1", host_id="h1", metric_name="cpu", metric_value=92, ts=event_ts())

        evaluator.evaluate(e1)
        evaluator.evaluate(e2)

        self.assertEqual(len(fired), 1)

    def test_recovery_invokes_resolve(self) -> None:
        redis_client = FakeRedis()
        rule = AlertRule(
            id="r2",
            tenant_id="t1",
            name="CPU Recover",
            metric_name="cpu",
            operator="gt",
            threshold=90,
            severity="warning",
            host_id="h1",
            consecutive=1,
            enabled=True,
        )
        evaluator = AlertEvaluator(redis_client=redis_client, rule_cache=FakeRuleCache([rule]))

        resolved: list[tuple[MetricEvent, AlertRule]] = []
        evaluator._fire_if_not_open = lambda event, active_rule: None  # type: ignore[method-assign]
        evaluator._resolve_if_open = lambda event, active_rule: resolved.append((event, active_rule))  # type: ignore[method-assign]

        evaluator.evaluate(MetricEvent("t1", "h1", "cpu", 50, event_ts()))
        self.assertEqual(len(resolved), 1)


def event_ts():
    from datetime import UTC, datetime

    return datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
