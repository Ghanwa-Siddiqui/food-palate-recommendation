from fastapi import APIRouter
from app.schemas.ranking import FeedResponse
from app.services.ranking.feed_service import RankingFeedService

router = APIRouter(prefix="/ranking", tags=["ranking"])
feed_service = RankingFeedService()

@router.get("/feed/{user_id}", response_model=FeedResponse)
async def get_user_feed(user_id: str):
    mock_dishes = [
        {"id": "d1", "name": "Beef Nihari", "restaurant_id": "r1", "restaurant_name": "Waris Nihari", "price": 650.0, "dietary_tags": ["halal"], "dish_vector": [0.9, 0.8]},
        {"id": "d2", "name": "Chicken Karahi", "restaurant_id": "r2", "restaurant_name": "Butt Karahi", "price": 1200.0, "dietary_tags": ["halal"], "dish_vector": [0.8, 0.9]}
    ]
    mock_user = {"user_id": user_id, "taste_vector": [0.9, 0.8], "budget_max": 1500.0, "dietary_restrictions": ["halal"]}
    
    items = feed_service.get_ranked_feed(user_id, mock_dishes, mock_user)
    return FeedResponse(user_id=user_id, total_candidates=len(items), items=items)