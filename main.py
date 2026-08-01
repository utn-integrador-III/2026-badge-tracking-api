from fastapi import FastAPI

from database.connection import initializeDatabase
from routes.users import router as usersRouter
from routes.verifications import router as verificationsRouter


def createApp() -> FastAPI:
    app = FastAPI(
        title="Badge Tracking API",
        version="0.1.0",
        description="Backend API for the Badge Tracking Project.",
    )
    app.include_router(usersRouter)
    app.include_router(verificationsRouter)
    return app


app = createApp()
initializeDatabase()


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {
        "message": "Badge Tracking API is running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def healthCheck() -> dict[str, str]:
    return {"status": "ok"}
