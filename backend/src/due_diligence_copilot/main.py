from fastapi import FastAPI

app = FastAPI(title="Due-Diligence Copilot API", version="0.1.0")


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    return {"status": "ok"}
