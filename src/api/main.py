"""
Nowva FastAPI Backend
Main application entry point for program generation API
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from dotenv import load_dotenv
from .routers import programs, health, livekit, auth, workouts

load_dotenv()

app = FastAPI(
    title="Nowva Program Generator API",
    description="API for generating personalized workout programs using AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware — origins from ALLOWED_ORIGINS env var (comma-separated)
allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(programs.router, prefix="/api/programs", tags=["programs"])
app.include_router(workouts.router, prefix="/api", tags=["workouts"])
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

    port = os.getenv("FASTAPI_PORT", "8001")
    print(f"📚 API Docs: http://localhost:{port}/docs")
    print(f"🔍 ReDoc: http://localhost:{port}/redoc")
    print(f"💚 Health Check: http://localhost:{port}/api/health")
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

    frontend_dist = Path(__file__).parent.parent.parent / "frontend_demo" / "dist"
    if not frontend_dist.exists():
        raise HTTPException(status_code=404, detail="Frontend not built")

    # Try to serve the exact file first (images, favicon, etc. from public/)
    static_file = (frontend_dist / full_path).resolve()
    if full_path and static_file.is_relative_to(frontend_dist) and static_file.is_file():
        return FileResponse(str(static_file))

    # Fall back to index.html for SPA routing
    return FileResponse(str(frontend_dist / "index.html"))
