from fastapi import APIRouter

from app.api.contracts import COMMON_ERROR_RESPONSES
from app.api.v1.auth import router as auth_router
from app.api.v1.milking import router as milking_router
from app.api.v1.modules import router as modules_router
from app.api.v1.sync import router as sync_router
from app.api.v1.system import router as system_router


api_v1_router = APIRouter()
api_v1_router.include_router(system_router)
api_v1_router.include_router(auth_router, responses=COMMON_ERROR_RESPONSES)
api_v1_router.include_router(modules_router, responses=COMMON_ERROR_RESPONSES)
api_v1_router.include_router(milking_router, responses=COMMON_ERROR_RESPONSES)
api_v1_router.include_router(sync_router, responses=COMMON_ERROR_RESPONSES)
