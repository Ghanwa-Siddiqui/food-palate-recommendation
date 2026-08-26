from typing import List, Dict
from app.services.ranking.generator import filter_candidates
from app.services.ranking.scoring import score_dish

class RankingFeedService:
    def get_ranked_feed(self, user_id: str, dishes: List[Dict], user_profile: Dict) -> List[Dict]:
        candidates = filter_candidates(dishes, user_profile)
        ranked = []
        for dish in candidates:
            scores = score_dish(dish, user_profile)
            ranked.append({
                "dish_id": dish["id"],
                "dish_name": dish["name"],
                "restaurant_id": dish["restaurant_id"],
                "restaurant_name": dish.get("restaurant_name", ""),
                "price": dish["price"],
                "match_percentage": scores["match_percentage"],
                "distance_km": scores["distance_km"]
            })
        ranked.sort(key=lambda x: x["match_percentage"], reverse=True)
        return ranked