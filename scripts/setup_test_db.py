import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def create_db():
    try:
        # isolation_level="AUTOCOMMIT" is essential for CREATE DATABASE
        engine = create_async_engine(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
            isolation_level="AUTOCOMMIT"
        )
        async with engine.connect() as conn:
            await conn.execute(text("DROP DATABASE IF EXISTS app_db_test"))
            await conn.execute(text("CREATE DATABASE app_db_test"))
        await engine.dispose()
        print("Database app_db_test created successfully.")
    except Exception as e:
        print(f"Error creating database: {e}")

if __name__ == "__main__":
    asyncio.run(create_db())
