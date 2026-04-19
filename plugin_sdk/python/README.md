# Python Plugin SDK

The first version intentionally keeps the SDK thin. Plugin authors should expose
a standard function:

```python
def run(payload: dict) -> dict:
    return {
        "status": "success",
        "outputs": {},
        "logs": [],
        "metrics": {},
    }
```

The platform and runner own input binding, output validation, writeback, and
audit logging.

