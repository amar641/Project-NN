from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncDatabase
from app.database import get_db
from app.schemas import VoteRequest, RoundResponse
from app.services.voting_service import VotingService
from app.services.round_manager import round_manager
from app.exceptions import VotingException
from app.logging_config import logger

router = APIRouter(prefix="/api/voting", tags=["voting"])

class ConnectionManager:
    """Manage WebSocket connections"""
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Active: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Active: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting: {str(e)}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

@router.post("/vote", response_model=RoundResponse)
async def vote(vote_request: VoteRequest, db: AsyncDatabase = Depends(get_db)):
    """Record a vote"""
    try:
        await VotingService.record_vote(db, vote_request.option)
        red_votes, green_votes = await VotingService.get_current_round_votes(db)
        
        await manager.broadcast({
            "type": "vote_update",
            "red_votes": red_votes,
            "green_votes": green_votes,
            "remaining_seconds": round_manager.get_remaining_time()
        })
        
        return RoundResponse(
            red_votes=red_votes,
            green_votes=green_votes,
            seconds_remaining=round_manager.get_remaining_time()
        )
    
    except VotingException as e:
        logger.warning(f"Voting error: {e.message}")
        raise

@router.get("/status", response_model=RoundResponse)
async def get_status(db: AsyncDatabase = Depends(get_db)):
    """Get current round status"""
    try:
        red_votes, green_votes = await VotingService.get_current_round_votes(db)
        return RoundResponse(
            red_votes=red_votes,
            green_votes=green_votes,
            seconds_remaining=round_manager.get_remaining_time()
        )
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        raise

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint"""
    try:
        await manager.connect(websocket)
        while True:
            data = await websocket.receive_text()
            logger.debug(f"WebSocket message: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)