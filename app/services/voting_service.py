from motor.motor_asyncio import AsyncDatabase
from app.exceptions import InvalidVoteException, DatabaseException
from app.logging_config import logger
from datetime import datetime
from typing import Tuple

class VotingService:
    """Service for handling voting logic with MongoDB"""
    
    @staticmethod
    async def record_vote(db: AsyncDatabase, option: str) -> None:
        """Record a vote"""
        try:
            if option not in ["red", "green"]:
                logger.warning(f"Invalid vote option received: {option}")
                raise InvalidVoteException(f"Invalid option: {option}")
            
            # Find active round
            current_round = await db["voting_rounds"].find_one({"winner": None})
            
            if not current_round:
                result = await db["voting_rounds"].insert_one({
                    "red_votes": 0,
                    "green_votes": 0,
                    "winner": None,
                    "created_at": datetime.utcnow()
                })
                current_round = await db["voting_rounds"].find_one({"_id": result.inserted_id})
            
            increment_field = "red_votes" if option == "red" else "green_votes"
            await db["voting_rounds"].update_one(
                {"_id": current_round["_id"]},
                {"$inc": {increment_field: 1}}
            )
            
            logger.info(f"Vote recorded: {option}")
        
        except InvalidVoteException:
            raise
        except Exception as e:
            logger.error(f"Error recording vote: {str(e)}")
            raise DatabaseException(f"Failed to record vote: {str(e)}")
    
    @staticmethod
    async def get_current_round_votes(db: AsyncDatabase) -> Tuple[int, int]:
        """Get current round vote counts"""
        try:
            current_round = await db["voting_rounds"].find_one({"winner": None})
            
            if not current_round:
                return 0, 0
            
            return current_round.get("red_votes", 0), current_round.get("green_votes", 0)
        except Exception as e:
            logger.error(f"Error fetching current round: {str(e)}")
            raise DatabaseException("Failed to fetch current round")
    
    @staticmethod
    async def finalize_round(db: AsyncDatabase, red_votes: int, green_votes: int) -> str:
        """Finalize current round"""
        try:
            current_round = await db["voting_rounds"].find_one({"winner": None})
            
            if not current_round:
                return "green" if red_votes <= green_votes else "red"
            
            winner = "green" if red_votes > green_votes else "red"
            
            await db["voting_rounds"].update_one(
                {"_id": current_round["_id"]},
                {"$set": {"winner": winner}}
            )
            
            logger.info(f"Round finalized - Winner: {winner}")
            return winner
        
        except Exception as e:
            logger.error(f"Error finalizing round: {str(e)}")
            raise DatabaseException("Failed to finalize round")