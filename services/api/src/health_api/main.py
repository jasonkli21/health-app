from fastapi import FastAPI

app = FastAPI(
    title="Personal Health API",
    version="0.0.0",
    description="Phase 0 scaffold. Canonical health-domain APIs are implemented in later phases.",
)


@app.get("/healthz", tags=["system"])
def healthcheck() -> dict[str, str]:
    """Return process liveness without exposing health-domain data."""
    return {"status": "ok"}
