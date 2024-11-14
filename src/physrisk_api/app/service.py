from fastapi import APIRouter, FastAPI

from .api import api_router

main = APIRouter()

# Register all routes or routers with the 'main' router.
main.include_router(api_router)


@main.get("/")
async def home():
    return {"message": "Hello World!"}
