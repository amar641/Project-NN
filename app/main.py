from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import asyncio
from app.config import settings
from app.database import connect_to_mongo, close_mongo_connection
from app.logging_config import logger
from app.services.round_manager import round_manager
from app.routers import voting, history

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown"""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await connect_to_mongo()
    round_task = asyncio.create_task(round_manager.start_round_timer())
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    round_manager.is_running = False
    round_task.cancel()
    await close_mongo_connection()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

app.include_router(voting.router)
app.include_router(history.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve index.html"""
    try:
        with open("app/static/index.html") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error serving index.html: {str(e)}")
        return "<h1>Error loading page</h1>"

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.APP_VERSION}

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle all exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)