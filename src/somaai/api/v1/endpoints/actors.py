from fastapi import APIRouter

from somaai.utils.ids import generate_id

router = APIRouter(prefix="/actors", tags=["actors"])


## This will generate a random actor id for anonymous users
## Later we shall use authentications...
@router.post("/anonymous")
async def create_actor():
    """Create a new anonymous actor ID."""
    return {"actor_id": generate_id()}
