from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class VotingRound(BaseModel):
    """MongoDB document model"""
    id: Optional[str] = Field(default=None, alias="_id")
    red_votes: int = 0
    green_votes: int = 0
    winner: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
