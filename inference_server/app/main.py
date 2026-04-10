from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Inference Server (M0)")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


class DetectRequest(BaseModel):
    task_id: str
    assets: List[Dict[str, Any]] = []
    item_names: List[str] = []


@app.post("/detect")
async def detect(body: DetectRequest) -> dict:
    # Minimal deterministic "real" endpoint for integration.
    image_ids = [a.get("image_id") for a in body.assets if a.get("image_id")] or [f"{body.task_id}_img_1"]
    item_names = body.item_names or ["物料A", "物料B"]

    detections: List[Dict[str, Any]] = []
    for img_id in image_ids:
        for name in item_names:
            detections.append(
                {
                    "image_id": img_id,
                    "item_name": name,
                    "candidates": [
                        {"box": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}, "confidence": 0.75},
                        {"box": {"x": 0.5, "y": 0.4, "w": 0.2, "h": 0.2}, "confidence": 0.45},
                    ],
                }
            )
    return {"detections": detections}

