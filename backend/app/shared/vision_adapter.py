import os
import abc
import logging
import base64
import io
import json
from typing import Dict, List, Any
from PIL import Image
from openai import AsyncOpenAI

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_engine
from app.models import SystemConfig

logger = logging.getLogger(__name__)

class VisionAdapter(abc.ABC):
    @abc.abstractmethod
    async def classify_image(self, image_path: str) -> Dict[str, Any]:
        """
        Classifies an image into: 'design_render', 'field_photo', or 'receipt'.
        Returns a dict: {"category": "...", "confidence": 0.xx}
        """
        pass

    @abc.abstractmethod
    async def detect_objects(self, image_paths: List[str], text_queries: List[str]) -> List[Dict[str, Any]]:
        """
        Detects objects in photos based on text descriptions.
        """
        pass
        
    @abc.abstractmethod
    async def extract_receipt_fields(self, image_path: str) -> Dict[str, Any]:
        """
        Extracts structured fields from a receipt: {type, amount, date, merchant, invoice_no}
        """
        pass

class LocalInferenceAdapter(VisionAdapter):
    """
    Connects to the local GPU-backed inference server via internal HTTP.
    Ideal for GroundingDINO, locally hosted Qwen-VL, etc.
    """
    def __init__(self):
        self.base_url = os.environ.get("INFERENCE_URL", "http://inference:8001")
        
    async def _post(self, endpoint: str, payload: dict) -> dict:
        import aiohttp
        url = f"{self.base_url.rstrip('/')}/{endpoint}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.error(f"Local Inference error HTTP {resp.status}: {await resp.text()}")
        except Exception as e:
            logger.error(f"Local Inference connection error: {e}")
        return {}

    async def classify_image(self, image_path: str) -> Dict[str, Any]:
        res = await self._post("classify", {"image_path": image_path})
        return res or {"category": "field_photo", "confidence": 0.5} # Fallback

    async def detect_objects(self, image_paths: List[str], text_queries: List[str]) -> List[Dict[str, Any]]:
        res = await self._post("detect", {"images": image_paths, "queries": text_queries})
        return res.get("detections", [])

    async def extract_receipt_fields(self, image_path: str) -> Dict[str, Any]:
        res = await self._post("ocr_receipt", {"image_path": image_path})
        return res or {}


class ExternalLLMAdapter(VisionAdapter):
    """
    Connects to an external OpenAI-compatible Vision API (e.g., GPT-4V, Zhipu GLM-4V)
    using the official async openai library.
    """
    def __init__(self):
        self.api_key = os.environ.get("VISION_API_KEY", "your-proxy-key")
        self.base_url = os.environ.get("VISION_BASE_URL", "https://api.openai.com/v1")
        self.model = os.environ.get("VISION_MODEL_NAME", "gpt-4-vision-preview")
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=3,
            timeout=60.0
        )

    def _encode_and_compress_image(self, image_path: str, max_size_mb: int = 10) -> str:
        with Image.open(image_path) as img:
            # Convert to RGB to avoid issues with transparent backgrounds or palettes in JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            # Downscale if image is exceptionally large to prevent token explosion or OOM
            width, height = img.size
            if max(width, height) > 2048:
                ratio = 2048 / max(width, height)
                img = img.resize((int(width * ratio), int(height * ratio)), Image.LANCZOS)
                
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            
            # Ensure it fits within payload constraints
            while len(img_byte_arr.getvalue()) > max_size_mb * 1024 * 1024:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=60)
                break
                
            return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

    async def classify_image(self, image_path: str) -> Dict[str, Any]:
        logger.info(f"External LLM Classify via OpenAI for {image_path}")
        try:
            b64_image = self._encode_and_compress_image(image_path)
            prompt = "Classify this image as exactly one of: 'design_render', 'field_photo', 'receipt'. Reply ONLY with a JSON object like {'category': '...', 'confidence': 0.9}."
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                        ]
                    }
                ],
                # response_format JSON enforcing typically works best with models like gpt-4o or gpt-4-turbo
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error(f"Vision API error classify_image: {e}")
            return {"category": "field_photo", "confidence": 0.5}

    async def detect_objects(self, image_paths: List[str], text_queries: List[str]) -> List[Dict[str, Any]]:
        logger.info(f"Mock External LLM Detection. Total images: {len(image_paths)}")
        # Bounding box detection is notoriously hard for generic pure LLMs without grounding output.
        return []
        
    async def extract_receipt_fields(self, image_path: str) -> Dict[str, Any]:
        logger.info(f"External LLM OCR Receipt via OpenAI for {image_path}")
        try:
            b64_image = self._encode_and_compress_image(image_path)
            prompt = "Extract fields from this receipt. Reply ONLY with a JSON object containing carefully extracted keys 'type' (e.g. invoice, payment), 'amount' (number as string), 'date' (YYYY-MM-DD), 'merchant', 'invoice_no'."
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                        ]
                    }
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error(f"Vision API error extract_receipt_fields: {e}")
            return {}

async def get_vision_adapter() -> VisionAdapter:
    """Factory to retrieve the configured Vision mechanism from SystemConfig."""
    engine = get_engine()
    mode = "local_gpu"
    try:
        async with AsyncSession(engine) as s:
            row = (await s.execute(
                select(SystemConfig).where(
                    SystemConfig.namespace == "llm",
                    SystemConfig.config_key == "vision_mode"
                )
            )).scalars().first()
            if row and row.config_value:
                mode = row.config_value
    except Exception as e:
        logger.error(f"Failed to fetch vision_mode config, defaulting to local_gpu: {e}")

    if mode == "llm_vision":
        return ExternalLLMAdapter()
    return LocalInferenceAdapter()

