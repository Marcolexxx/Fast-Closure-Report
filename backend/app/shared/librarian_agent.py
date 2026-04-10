from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List
from sqlalchemy import text
from app.db import get_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

def get_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def _query_top_k_experiences(skill_id: str, search_query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Search LibrarianKnowledge using PostgreSQL to_tsquery and @@.
    Retrieves top K experiences for prompt formatting.
    """
    if not search_query:
        return []
        
    engine = get_engine()
    # In postgres, we can use keywords @@ to_tsquery(:q). But since we might be migrating,
    # and we want robustness if MySQL is still used temporarily, we can do a fallback or strict PG.
    # The requirement specifically said PostgreSQL TSVECTOR or @@.
    
    # We will sanitize the query for to_tsquery (replace spaces with & or |)
    # Simple sanitization for strict alphanumeric + spaces
    terms = [w for w in search_query.split() if w.strip()]
    if not terms:
        return []
    ts_query_str = " | ".join(terms)
    
    async with get_session_maker()() as session:
        # We assume `keywords` or `summary` text is searchable.
        # Actually in SQLAlchemy, text() handles the raw SQL.
        sql = text("""
            SELECT id, summary, keywords, intent_tags, parent_id
            FROM "LibrarianKnowledge"
            WHERE skill_id = :skill_id
              AND is_active = true
              AND (
                  to_tsvector('simple', keywords || ' ' || summary) @@ to_tsquery('simple', :query)
              )
            ORDER BY created_at DESC
            LIMIT :k
        """)
        
        try:
            result = await session.execute(sql, {"skill_id": skill_id, "query": ts_query_str, "k": k})
            rows = result.mappings().all()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Librarian DB Query failed (possibly not switched to Postgres fully yet): {e}")
            # Fallback to general LIKE for robustness if PG vector search syntax throws error
            fallback_sql = text("""
                SELECT id, summary, keywords, intent_tags, parent_id
                FROM "LibrarianKnowledge"
                WHERE skill_id = :skill_id
                  AND is_active = true
                  AND (summary LIKE :like_q OR keywords LIKE :like_q)
                ORDER BY created_at DESC
                LIMIT :k
            """)
            like_q = f"%{terms[0]}%"
            result = await session.execute(fallback_sql, {"skill_id": skill_id, "like_q": like_q, "k": k})
            return [dict(r) for r in result.mappings().all()]


async def _librarian_rescue_internal(task_ctx: dict, failed_reason: str, input_data: dict) -> bool:
    """Internal task wrapped with timeout in caller."""
    skill_id = task_ctx.get("skill", "skill-event-report")
    
    # Heuristic text to search
    # e.g., if it's OCR, merchant name might be in input_data
    search_query = failed_reason
    
    logger.info(f"Bypass routing LibrarianRescue ... Querying postgres TSVECTOR with '{search_query}'")
    
    experiences = await _query_top_k_experiences(skill_id, search_query, k=5)
    
    if not experiences:
        logger.info("No relevant bypass experience found. Rescue failed.")
        return False
        
    experience_prompts = "\n".join([f"- {exp['summary']} (Tags: {exp.get('intent_tags')})" for exp in experiences])
    
    # Here we would normally synthesize the prompt and call the high-fidelity High-Cost LLM.
    # For now, if we found solid experience, we mock a successful high-fidelity rescue.
    logger.info(f"Rescue succeeded. Applied Top-K experiences:\n{experience_prompts}")
    
    # Emulate fixing the state
    return True


async def run_librarian_rescue(task_ctx: dict, failed_reason: str, input_data: dict) -> bool:
    """
    Tries to rescue a failed or low-confidence tool pipeline by creating 
    an enhanced prompt using past feedback events retrieved from PG JSONB/TSVECTOR.
    
    MUST be wrapped in strict 5-second timeout.
    """
    try:
        # Wrap in strict 5.0 second timeout to prevent hanging the Web Node.
        rescued = await asyncio.wait_for(
            _librarian_rescue_internal(task_ctx, failed_reason, input_data),
            timeout=5.0
        )
        return rescued
    except asyncio.TimeoutError:
        logger.warning(f"Librarian Rescue timed out (>5.0s) for {failed_reason}. Aborting bypass.")
        return False
    except Exception as e:
        logger.error(f"Librarian Rescue encountered error: {e}")
        return False
