from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncDatabase
from app.database import get_db
from app.schemas import HistoryResponse
from app.logging_config import logger
from typing import List

router = APIRouter(prefix="/api/history", tags=["history"])

@router.get("/", response_model=List[HistoryResponse])
async def get_history(limit: int = Query(50, ge=1, le=500), db: AsyncDatabase = Depends(get_db)):
    """Get voting history"""
    try:
        rounds = await db["voting_rounds"].find(
            {"winner": {"$ne": None}}
        ).sort("created_at", -1).limit(limit).to_list(length=limit)
        
        return [
            HistoryResponse(
                id=str(r["_id"]),
                winner=r["winner"],
                red_votes=r["red_votes"],
                green_votes=r["green_votes"],
                created_at=r["created_at"]
            )
            for r in rounds
        ]
    except Exception as e:
        logger.error(f"Error fetching history: {str(e)}")
        raise

@router.get("/latest", response_model=HistoryResponse)
async def get_latest_round(db: AsyncDatabase = Depends(get_db)):
    """Get latest completed round"""
    try:
        round_obj = await db["voting_rounds"].find_one(
            {"winner": {"$ne": None}},
            sort=[("created_at", -1)]
        )
        
        if not round_obj:
            return None
        
        return HistoryResponse(
            id=str(round_obj["_id"]),
            winner=round_obj["winner"],
            red_votes=round_obj["red_votes"],
            green_votes=round_obj["green_votes"],
            created_at=round_obj["created_at"]
        )
    except Exception as e:
        logger.error(f"Error fetching latest round: {str(e)}")
        raise