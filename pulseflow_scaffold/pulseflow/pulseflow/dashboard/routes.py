from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard")
async def dashboard():
    return {"message": "Dashboard UI will be added in Phase 3."}
