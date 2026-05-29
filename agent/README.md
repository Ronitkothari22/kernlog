# kernlog-agent

Install locally:

```bash
pip install -e agent/
```

Run:

```bash
kernlog-agent --config /etc/kernlog/config.yaml
```

## FastAPI middleware snippet

```python
from fastapi import FastAPI
from kernlog_agent.producers.qstash import QStashProducer
from kernlog_middleware import install_kernlog_middleware

app = FastAPI()
producer = QStashProducer(base_url=..., token=..., signing_key=...)
install_kernlog_middleware(app, producer=producer, tenant_id_getter=lambda req: req.headers.get("x-tenant-id", "unknown"))
```
