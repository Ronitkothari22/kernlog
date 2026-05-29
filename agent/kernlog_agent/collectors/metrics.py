"""System metrics collector."""

from __future__ import annotations

import time

import psutil


def collect_system_metrics(tenant_id: str, host_id: str) -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    network = psutil.net_io_counters()

    return {
        "tenant_id": tenant_id,
        "host_id": host_id,
        "ts_monotonic": time.monotonic(),
        "metrics": {
            "cpu_percent": float(cpu_percent),
            "memory_total": int(memory.total),
            "memory_used": int(memory.used),
            "memory_percent": float(memory.percent),
            "disk_root_total": int(disk.total),
            "disk_root_used": int(disk.used),
            "disk_root_percent": float(disk.percent),
            "net_bytes_sent": int(network.bytes_sent),
            "net_bytes_recv": int(network.bytes_recv),
            "net_packets_sent": int(network.packets_sent),
            "net_packets_recv": int(network.packets_recv),
        },
    }
