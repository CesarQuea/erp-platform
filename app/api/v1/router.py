from fastapi import APIRouter

from app.api.v1.system import router as system_router


api_v1_router = APIRouter()
api_v1_router.include_router(system_router)
