from pydantic import BaseModel
from typing import List, Optional

class RankedDishItem(BaseModel):
    dish_id: str
    dish_name: str
    restaurant_id: str
    restaurant_name: str
    price: float
    match_percentage: int
    distance_km: Optional[float] = None

class FeedResponse(BaseModel):
    user_id: str
    total_candidates: int
    items: List[RankedDishItem]