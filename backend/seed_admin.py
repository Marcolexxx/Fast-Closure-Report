import asyncio
from app.db import get_engine
from app.models import Base, User, UserRole
from app.models import User, UserRole
from app.security.auth import get_password_hash
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import select

async def main():
    engine = get_engine()
    # Ensure tables are created (just in case)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        existing = result.scalars().first()
        
        if existing:
            print("Admin user already exists! Password might be different than admin123")
            existing.hashed_password = get_password_hash("admin123")
            await session.commit()
            print("Reset password to 'admin123'")
        else:
            admin_user = User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                full_name="System Administrator",
                role=UserRole.ADMIN.value
            )
            session.add(admin_user)
            await session.commit()
            print("Successfully created admin user with password 'admin123'")

if __name__ == "__main__":
    asyncio.run(main())
