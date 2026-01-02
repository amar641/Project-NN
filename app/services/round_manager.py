import asyncio
from datetime import datetime
from app.config import settings
from app.logging_config import logger
from app.database import mongodb
from app.services.voting_service import VotingService

class RoundManager:
    """Manages voting rounds timing"""
    
    def __init__(self):
        self.round_start_time = datetime.utcnow()
        self.round_duration = settings.ROUND_DURATION_SECONDS
        self.is_running = False
    
    def get_remaining_time(self) -> int:
        """Get remaining seconds"""
        elapsed = (datetime.utcnow() - self.round_start_time).total_seconds()
        remaining = max(0, self.round_duration - int(elapsed))
        return remaining
    
    def is_round_ended(self) -> bool:
        """Check if round ended"""
        return self.get_remaining_time() <= 0
    
    async def start_round_timer(self):
        """Start round timer"""
        self.is_running = True
        logger.info(f"Starting new round (Duration: {self.round_duration}s)")
        self.round_start_time = datetime.utcnow()
        
        try:
            while not self.is_round_ended() and self.is_running:
                await asyncio.sleep(1)
            
            if self.is_running:
                await self._finalize_current_round()
                await asyncio.sleep(2)
                await self.start_round_timer()
        
        except Exception as e:
            logger.error(f"Error in round timer: {str(e)}")
            self.is_running = False
    
    async def _finalize_current_round(self):
        """Finalize the current round"""
        try:
            red_votes, green_votes = await VotingService.get_current_round_votes(mongodb.db)
            await VotingService.finalize_round(mongodb.db, red_votes, green_votes)
        except Exception as e:
            logger.error(f"Error finalizing round: {str(e)}")

round_manager = RoundManager()