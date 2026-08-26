import math
from typing import List, Optional, Dict

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def calculate_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

def score_dish(dish: Dict, user_profile: Dict) -> Dict:
    taste_sim = calculate_cosine_similarity(user_profile.get("taste_vector", []), dish.get("dish_vector", []))
    taste_score = max(0.0, taste_sim) * 100.0
    
    total_score = (0.45 * taste_score) + (0.20 * taste_score) + (0.35 * 70.0)
    return {
        "match_percentage": min(99, int(round(total_score))),
        "distance_km": None
    }