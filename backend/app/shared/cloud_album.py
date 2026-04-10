from __future__ import annotations

import hashlib
import logging
import os
import aiohttp
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import ProjectFile, Project
from app.config import get_settings

logger = logging.getLogger(__name__)

async def process_cloud_image(
    project_id: str, 
    source_url: str, 
    user_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Downloads an image from a URL, computes its SHA256 hash, and performs 
    deduplication before saving to project assets as per PRD §7.2.
    """
    settings = get_settings()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"failed_to_fetch_image: {source_url} status={response.status}")
                    return None
                content = await response.read()
    except Exception as e:
        logger.error(f"cloud_album_download_error: {e}")
        return None

    # Content addressing (Deduplication)
    sha256 = hashlib.sha256(content).hexdigest()
    
    # Check DB for existing file with same hash in this project
    async_session = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    async with async_session() as db_session:
        # PRD §7.2: SHA-based deduplication
        existing = await db_session.execute(
            select(ProjectFile).where(
                ProjectFile.project_id == project_id,
                ProjectFile.sha256 == sha256,
                ProjectFile.is_deleted == False
            )
        )
        file_record = existing.scalars().first()
        
        if file_record:
            logger.info(f"cloud_album_dedup_hit: {sha256[:8]}")
            return _file_to_dict(file_record)

        # Not found, save it
        storage_root = settings.file_storage_root
        dest_dir = os.path.join(storage_root, "projects", project_id)
        os.makedirs(dest_dir, exist_ok=True)
        
        filename = source_url.split("/")[-1].split("?")[0] or "downloaded_image.jpg"
        if not filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            filename += ".jpg"
            
        dest_path = os.path.join(dest_dir, f"{sha256[:8]}_{filename}")
        
        with open(dest_path, "wb") as f:
            f.write(content)
            
        new_file = ProjectFile(
            project_id=project_id,
            original_name=filename,
            file_type="image",
            sha256=sha256,
            storage_path=dest_path,
            file_size=len(content),
            uploaded_by=user_id,
        )
        db_session.add(new_file)
        await db_session.commit()
        await db_session.refresh(new_file)
        
        return _file_to_dict(new_file)

def _file_to_dict(f: ProjectFile) -> Dict[str, Any]:
    return {
        "id": f.id,
        "name": f.original_name,
        "url": f"http://localhost:8000/api/files/{f.id}", # Proxy URL
        "local_path": f.storage_path,
        "sha256": f.sha256
    }
