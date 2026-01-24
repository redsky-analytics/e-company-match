# Development Instructions

## Logging

Always use `structlog` for logging — never the stdlib `logging` module.

```python
import structlog

log = structlog.get_logger()
log.info("event_name", key="value")
```

## Running Multiple Processes

Use `teemux` (npm CLI) to merge logs from multiple processes into a single stream:

```bash
teemux --name worker -- python -m myapp.worker
teemux --name api -- python -m myapp.api
```

### Installing teemux

```bash
npm install -g teemux
```
