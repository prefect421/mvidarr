#!/usr/bin/env python3
"""
Simple FastAPI test to verify basic functionality
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="MVidarr API Test",
    description="Simple test of FastAPI functionality",
    version="0.9.8"
)

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.9.8"
    message: str = "FastAPI is running successfully"

@app.get("/")
async def root():
    return {"message": "MVidarr FastAPI Test - Running Successfully"}

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse()

@app.get("/test")
async def test_endpoint():
    return {
        "status": "success",
        "message": "Phase 3 Week 32 Pydantic Models - Test Endpoint",
        "endpoints": [
            "/",
            "/health", 
            "/test",
            "/docs",
            "/redoc"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI test server on http://192.168.1.145:5000")
    uvicorn.run("simple_fastapi_test:app", host="0.0.0.0", port=5000, reload=False)