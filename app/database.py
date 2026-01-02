from motor.motor_asyncio import AsyncClient, AsyncDatabase
from app.config import settings
from app.logging_config import logger
from typing import Optional

class MongoDB:
    client: Optional[AsyncClient] = None
    db: Optional[AsyncDatabase] = None

mongodb = MongoDB()

async def connect_to_mongo():
    """Connect to MongoDB"""
    try:
        mongodb.client = AsyncClient(settings.MONGODB_URL)
        mongodb.db = mongodb.client[settings.MONGODB_DATABASE]
        await mongodb.client.admin.command('ping')
        await create_indexes()
        logger.info(f"✓ Connected to MongoDB: {settings.MONGODB_DATABASE}")
    except Exception as e:
        logger.error(f"✗ Failed to connect to MongoDB: {str(e)}")
        raise

async def close_mongo_connection():
    """Close MongoDB connection"""
    try:
        if mongodb.client:
            mongodb.client.close()
            logger.info("✓ MongoDB connection closed")
    except Exception as e:
        logger.error(f"✗ Error closing MongoDB: {str(e)}")

async def create_indexes():
    """Create database indexes"""
    try:
        await mongodb.db["voting_rounds"].create_index("created_at")
        await mongodb.db["voting_rounds"].create_index("winner")
        logger.info("✓ Database indexes created")
    except Exception as e:
        logger.error(f"✗ Error creating indexes: {str(e)}")

async def get_db() -> AsyncDatabase:
    return mongodb.db