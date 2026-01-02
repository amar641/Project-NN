from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class VoteRequest(BaseModel):
    """Schema for vote request"""
    option: Literal["red", "green"]
    
    class Config:
        schema_extra = {
            "example": {"option": "red"}
        }

class RoundResponse(BaseModel):
    """Schema for current round response"""
    red_votes: int
    green_votes: int
    seconds_remaining: int
    
    class Config:
        schema_extra = {
            "example": {
                "red_votes": 10,
                "green_votes": 8,
                "seconds_remaining": 45
            }
        }

class HistoryResponse(BaseModel):
    """Schema for voting history"""
    id: int
    winner: str
    red_votes: int
    green_votes: int
    created_at: datetime
    
    class Config:
        from_attributes = True
        schema_extra = {
            "example": {
                "id": 1,
                "winner": "green",
                "red_votes": 10,
                "green_votes": 8,
                "created_at": "2024-01-01T12:00:00"
            }
        }