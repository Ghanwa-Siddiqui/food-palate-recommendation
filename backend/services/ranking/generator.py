from typing import List, Dict

def filter_candidates(dishes: List[Dict], user_profile: Dict) -> List[Dict]:
    budget_max = user_profile.get("budget_max", float("inf"))
    user_dietary = set(user_profile.get("dietary_restrictions", []))

    candidates = []
    for dish in dishes:
        if dish.get("price", 0) > budget_max:
            continue
        dish_dietary = set(dish.get("dietary_tags", []))
        if not user_dietary.issubset(dish_dietary):
            continue
        candidates.append(dish)
    return candidates