"""
Nowva FastAPI Backend
Main application entry point for program generation API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import programs, health

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


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("\n" + "="*80)
    print("🚀 Nowva FastAPI Backend Starting...")
    print("="*80)
    print("📚 API Docs: http://localhost:8000/docs")
    print("🔍 ReDoc: http://localhost:8000/redoc")
    print("💚 Health Check: http://localhost:8000/api/health")
    print("="*80 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    print("\n" + "="*80)
    print("🛑 Nowva FastAPI Backend Shutting Down...")
    print("="*80 + "\n")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Nowva Program Generator API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }
