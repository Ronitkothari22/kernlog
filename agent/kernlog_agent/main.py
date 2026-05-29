"""CLI and runtime loop for kernlog-agent."""

from __future__ import annotations

import argparse
import signal
import threading
import time

from kernlog_agent import __version__
from kernlog_agent.config import AgentConfigError, load_config


class AgentRuntime:
    def __init__(self, config_path: str) -> None:
        from kernlog_agent.producers.qstash import QStashProducer

        self.config = load_config(config_path)
        self.stop_event = threading.Event()
        self.producer = QStashProducer(
            base_url=self.config.upstash_qstash_url,
            token=self.config.upstash_qstash_token,
            signing_key=self.config.upstash_qstash_current_signing_key,
        )
        self.tailer: LogTailer | None = None
        self.tenant_id = ""
        self.host_id = self.config.host_id

    def _emit_log(self, file_path: str, line: str, ts: str) -> None:
        payload = {
            "tenant_id": self.tenant_id,
            "host_id": self.host_id,
            "ts": ts,
            "file_path": file_path,
            "line": line,
        }
        self.producer.publish("logs.app", payload)

    def run(self) -> int:
        from kernlog_agent.collectors.logs import LogTailer
        from kernlog_agent.collectors.metrics import collect_system_metrics
        from kernlog_agent.registration import register_agent

        result = register_agent(
            base_url=self.config.backend_base_url,
            agent_key=self.config.agent_key,
            host_id=self.config.host_id,
            label=self.config.host_label,
            agent_version=__version__,
        )
        self.tenant_id = result.tenant_id
        self.host_id = result.host_id

        if self.config.log_file_paths:
            self.tailer = LogTailer(self.config.log_file_paths, self._emit_log)
            self.tailer.start()

        while not self.stop_event.is_set():
            started = time.monotonic()
            payload = collect_system_metrics(self.tenant_id, self.host_id)
            publish_result = self.producer.publish("metrics.system", payload)
            if not publish_result.success:
                return 1
            elapsed = time.monotonic() - started
            sleep_for = max(0.0, self.config.collection_interval_seconds - elapsed)
            self.stop_event.wait(timeout=sleep_for)

        return 0

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.tailer is not None:
            self.tailer.stop()
        self.producer.close()


def cli() -> None:
    parser = argparse.ArgumentParser(prog="kernlog-agent", description="Kernlog host monitoring agent")
    parser.add_argument("--config", default="/etc/kernlog/config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    runtime = None

    def _handle_signal(_signum, _frame) -> None:
        if runtime is not None:
            runtime.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        runtime = AgentRuntime(args.config)
        exit_code = runtime.run()
    except AgentConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}")
    except RuntimeError as exc:
        raise SystemExit(f"Agent startup/runtime error: {exc}")
    finally:
        if runtime is not None:
            runtime.shutdown()

    raise SystemExit(exit_code)


if __name__ == "__main__":
    cli()
