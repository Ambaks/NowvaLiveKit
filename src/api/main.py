"""
Nowva FastAPI Backend
Main application entry point for program generation API
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .routers import programs, health, livekit

app = FastAPI(
    title="Nowva Program Generator API",
    description="API for generating personalized workout programs using AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(programs.router, prefix="/api/programs", tags=["programs"])
app.include_router(livekit.router, prefix="/api/livekit", tags=["livekit"])

# Serve frontend static files
frontend_dist = Path(__file__).parent.parent.parent / "frontend_demo" / "dist"
if frontend_dist.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    print(f"✓ Serving frontend assets from {frontend_dist / 'assets'}")
else:
    print("⚠️  Frontend dist folder not found. Run 'npm run build' in frontend_demo/")


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("\n" + "="*80)
    print("🚀 Nowva FastAPI Backend Starting...")
    print("="*80)

    # Initialize session logger for pricing tracking
    from core.session_logger import SessionLogger
    session_logger = SessionLogger.get_instance()
    session_logger.start_session()
    print("📊 Session logging enabled - pricing will be tracked")

    # Clean up stuck jobs from previous server runs
    from sqlalchemy import create_engine, text
    import os
    from dotenv import load_dotenv

    load_dotenv()

    try:
        engine = create_engine(os.getenv("DATABASE_URL"))
        with engine.connect() as conn:
            result = conn.execute(text("""
                UPDATE program_generation_jobs
                SET status = 'failed',
                    error_message = 'Job terminated - server was restarted while job was running',
                    completed_at = NOW()
                WHERE status = 'in_progress'
            """))
            conn.commit()

            if result.rowcount > 0:
                print(f"🧹 Cleaned up {result.rowcount} stuck job(s) from previous server run")
    except Exception as e:
        print(f"⚠️  Failed to clean up stuck jobs: {e}")

    print("📚 API Docs: http://localhost:8000/docs")
    print("🔍 ReDoc: http://localhost:8000/redoc")
    print("💚 Health Check: http://localhost:8000/api/health")
    print("="*80 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    print("\n" + "="*80)
    print("🛑 Nowva FastAPI Backend Shutting Down...")
    print("="*80)

    # Save session logs and print summary
    from core.session_logger import SessionLogger
    session_logger = SessionLogger.get_instance()
    summary = session_logger.end_session()
    print(summary)
    print("="*80 + "\n")


@app.get("/", include_in_schema=False)
async def root():
    """Serve frontend index.html"""
    frontend_dist = Path(__file__).parent.parent.parent / "frontend_demo" / "dist"
    if frontend_dist.exists():
        return FileResponse(str(frontend_dist / "index.html"))
    else:
        return {
            "service": "Nowva Program Generator API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
            "warning": "Frontend not built. Run: cd frontend_demo && npm run build"
        }


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """Serve frontend for all non-API routes (SPA routing)"""
    # API routes are handled by routers
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc"):
        raise HTTPException(status_code=404, detail="Not found")

    # Serve index.html for SPA routing
    frontend_dist = Path(__file__).parent.parent.parent / "frontend_demo" / "dist"
    if frontend_dist.exists():
        return FileResponse(str(frontend_dist / "index.html"))
    else:
        raise HTTPException(status_code=404, detail="Frontend not built")
