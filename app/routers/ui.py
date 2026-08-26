"""Namak UI — visual-only pages, not yet wired to the backend.

Content here mirrors the design mockup (namak-web-app-ui.html) with mock
data. TODO(backend): swap the hardcoded context dicts for real calls into
app/personalization.py, app/repositories, app/popularity.py, and Esha's
ranking/feed once those contracts are ready to consume from here.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/app", tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

DEMO_USER = {"username": "areeba", "name": "Areeba", "initial": "A"}

HERO_DISHES = [
    {"klass": "", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken2.jpg", "name": "Beef nihari", "place": "Waris · Anarkali", "match": "98%"},
    {"klass": "k1", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken5.jpg", "name": "Chicken karahi", "place": "Butt Karahi", "match": "94%"},
    {"klass": "k2", "img": "https://foodish-api.com/images/biryani/biryani3.jpg", "name": "Sindhi biryani", "place": "Kolachi", "match": "91%"},
]

DISH_TILES = [
    {"klass": "", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken10.jpg", "name": "Nihari", "picked": True},
    {"klass": "k1", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken15.jpg", "name": "Karahi", "picked": True},
    {"klass": "k2", "img": "https://foodish-api.com/images/biryani/biryani7.jpg", "name": "Biryani", "picked": False},
    {"klass": "k4", "img": "https://foodish-api.com/images/pasta/pasta20.jpg", "name": "Chow mein", "picked": True},
    {"klass": "k3", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken22.jpg", "name": "Palak paneer", "picked": False},
    {"klass": "k4", "img": "https://foodish-api.com/images/samosa/samosa3.jpg", "name": "Seekh kebab", "picked": True},
    {"klass": "", "img": "https://foodish-api.com/images/pizza/pizza4.jpg", "name": "Pizza", "picked": False},
    {"klass": "k2", "img": "https://foodish-api.com/images/rice/rice8.jpg", "name": "Daal chawal", "picked": False},
    {"klass": "", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken30.jpg", "name": "Haleem", "picked": True},
    {"klass": "", "img": "https://foodish-api.com/images/pasta/pasta5.jpg", "name": "Pasta", "picked": False},
    {"klass": "k4", "img": "https://foodish-api.com/images/samosa/samosa8.jpg", "name": "Samosa", "picked": False},
    {"klass": "", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken18.jpg", "name": "Paya", "picked": False},
]

HERO_PICK = {
    "slug": "waris-nihari", "dish": "Beef nihari", "restaurant": "Waris", "loved_label": "Waris Nihari",
    "area": "Anarkali", "distance": "1.2 km", "match": 98,
    "tag1": "Very spicy", "tag2": "Slow-cooked", "tag3": "Iconic",
    "img": "https://foodish-api.com/images/butter-chicken/butter-chicken1.jpg",
}

PICKS = [
    {"klass": "k1", "slug": "butt-karahi", "dish": "Chicken karahi", "restaurant": "Butt Karahi · Fortress", "match": 94, "img": "https://foodish-api.com/images/butter-chicken/butter-chicken8.jpg"},
    {"klass": "k2", "slug": "kolachi", "dish": "Sindhi biryani", "restaurant": "Kolachi · DHA", "match": 91, "img": "https://foodish-api.com/images/biryani/biryani12.jpg"},
    {"klass": "k4", "slug": "shahi-haleem-house", "dish": "Beef haleem", "restaurant": "Shahi Haleem House", "match": 89, "img": "https://foodish-api.com/images/butter-chicken/butter-chicken25.jpg"},
    {"klass": "", "slug": "dragon-wok", "dish": "Chicken chow mein", "restaurant": "Dragon Wok", "match": 86, "img": "https://foodish-api.com/images/pasta/pasta12.jpg"},
]

SIMILAR_PICKS = [
    {"klass": "k4", "slug": "phajjay-ke-paye", "dish": "Paya", "restaurant": "Phajjay Ke Paye", "match": 93, "img": "https://foodish-api.com/images/butter-chicken/butter-chicken13.jpg"},
    {"klass": "k1", "slug": "bundu-khan", "dish": "Seekh kebab", "restaurant": "Bundu Khan", "match": 90, "img": "https://foodish-api.com/images/samosa/samosa12.jpg"},
    {"klass": "", "slug": "waris-nihari", "dish": "Maghaz masala", "restaurant": "Waris (same kitchen)", "match": 87, "img": "https://foodish-api.com/images/butter-chicken/butter-chicken19.jpg"},
]

TASTE_TWINS = [
    {"klass": "b", "initial": "H", "name": "Hamza R.", "overlap": 94},
    {"klass": "c", "initial": "Z", "name": "Zara K.", "overlap": 89},
    {"klass": "e", "initial": "M", "name": "Mustafa A.", "overlap": 87},
]

FOLLOWING_ACTIVITY = [
    {"klass": "b", "initial": "H", "name": "Hamza", "verb": 'rated <b style="color:var(--ink);font-weight:500;">Butt Karahi</b> ★★★★★', "meta": '"Best karahi in Fortress." · 2h'},
    {"klass": "c", "initial": "Z", "name": "Zara", "verb": 'added 4 places to <b style="color:var(--ink);font-weight:500;">"MM Alam late-night"</b>', "meta": "Collection · 5h"},
]

TRENDING = ["Cafe Aylanto", "Andaaz Restaurant", "Yum Chinese & Thai"]

RESTAURANTS = {
    "waris-nihari": {
        "name": "Waris Nihari", "tagline": "Iconic · since 1962", "area": "Anarkali, Lahore",
        "cuisine": "Pakistani", "price_range": "Rs. 500-800", "hours_short": "Open until midnight",
        "hero_img": "https://foodish-api.com/images/butter-chicken/butter-chicken17.jpg",
        "address": "Anarkali Food Street, Lahore", "hours_full": "11 AM – midnight, daily",
        "phone": "+92 42 3722 4455",
        "dishes": [
            {"klass": "", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken4.jpg", "name": "Beef nihari", "price": "Rs. 650", "note": "slow-cooked 8 hrs · very spicy", "match": 98,
             "chips": [{"klass": "hot", "label": "very spicy"}, {"klass": "", "label": "tender"}, {"klass": "", "label": "rich gravy"}]},
            {"klass": "k4", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken21.jpg", "name": "Maghaz masala", "price": "Rs. 720", "note": "a Lahori acquired taste", "match": 82,
             "chips": [{"klass": "hot", "label": "spicy"}, {"klass": "", "label": "rich"}]},
            {"klass": "k1", "img": "https://foodish-api.com/images/butter-chicken/butter-chicken27.jpg", "name": "Paya", "price": "Rs. 580", "note": "sunday breakfast staple", "match": 91,
             "chips": [{"klass": "", "label": "gelatinous"}, {"klass": "", "label": "warming"}]},
        ],
        "reviews": [
            {"klass": "b", "initial": "H", "name": "Hamza R.", "badge": "Taste twin · 94% overlap", "stars": 5,
             "text": "Melts in your mouth. Bring water — very spicy — but that's the point. The gravy is what I judge every other nihari against now.",
             "chips": [{"klass": "hot", "label": "very spicy"}, {"klass": "veg", "label": "tender"}, {"klass": "", "label": "rich gravy"}]},
            {"klass": "c", "initial": "Z", "name": "Zara K.", "badge": "Follows you", "stars": 4,
             "text": "Solid nihari, gravy is rich. Naan portion could be better — order two.", "chips": []},
        ],
        "match": {
            "score": 96,
            "explanation": 'This fits you because you rated <b style="color:var(--cream);">Butt Karahi</b> 5★ and love <b style="color:var(--cream);">very spicy, slow-cooked beef</b>. 12 of your taste twins recommend it.',
            "factors": ["spicy · +32", "slow-cooked · +28", "beef · +21"],
        },
        "aspects": [
            {"label": "Spiciness", "value": "Very high", "klass": "k-hot", "bar_klass": "hot", "pct": 92},
            {"label": "Tenderness", "value": "Excellent", "klass": "k-mint", "bar_klass": "veg", "pct": 88},
            {"label": "Portion", "value": "Generous", "klass": "", "bar_klass": "", "pct": 78},
            {"label": "Value", "value": "Good", "klass": "", "bar_klass": "", "pct": 68},
        ],
    },
}

PROFILES = {
    "areeba": {
        "name": "Areeba Siddiqui", "username": "areeba", "initial": "A", "city": "Lahore", "joined": "March 2026",
        "bio": "Chasing the perfect nihari across the country. Beef over chicken, always. Karahi supremacist.",
        "stats": {"rated": 47, "followers": 218, "following": 89, "collections": 12},
        "vector_bars": [70, 90, 55, 95, 40, 80, 65, 85, 50, 75, 60, 88, 45, 72],
        "dna_summary": 'Loves <span class="k-sf">slow-cooked, spicy, protein-forward Pakistani</span> classics with rich gravies — with a soft spot for Chinese street food and warm desserts.',
        "flavor_tags": ["very spicy", "slow-cooked", "beef-forward", "rich gravy", "warm desserts"],
    },
}

COLLECTIONS = [
    {"title": "Perfect nihari, ranked", "places": 14, "saves": 82,
     "imgs": ["https://foodish-api.com/images/butter-chicken/butter-chicken2.jpg", "https://foodish-api.com/images/butter-chicken/butter-chicken13.jpg",
              "https://foodish-api.com/images/butter-chicken/butter-chicken25.jpg", "https://foodish-api.com/images/samosa/samosa3.jpg"]},
    {"title": "Late-night desi in Lahore", "places": 9, "saves": 41,
     "imgs": ["https://foodish-api.com/images/butter-chicken/butter-chicken8.jpg", "https://foodish-api.com/images/samosa/samosa12.jpg",
              "https://foodish-api.com/images/biryani/biryani12.jpg", "https://foodish-api.com/images/dessert/dessert4.jpg"]},
]

ACTIVITY = [
    {"img": "https://foodish-api.com/images/butter-chicken/butter-chicken8.jpg",
     "headline": 'Rated <b>Chicken karahi</b> at <b>Butt Karahi</b> <span class="rating">★★★★★</span>',
     "quote": "The gravy is exactly what karahi should be — sharp, oily in the right way, and hot enough to make you sweat.",
     "meta": "2 hours ago · 8 likes · 3 comments"},
    {"img": "https://foodish-api.com/images/biryani/biryani18.jpg",
     "headline": 'Added <b>Sindhi biryani at Kolachi</b> to <b>"Weekend brunch"</b>', "quote": None, "meta": "Yesterday"},
]

TWIN_OVERLAP = {"pct": 89, "note": 'You both rank <b style="color:var(--ink);">Waris Nihari</b> and <b style="color:var(--ink);">Bundu Khan</b> in your top 5.'}

MUTUAL_FOLLOWERS = [
    {"klass": "b", "initial": "H", "name": "Hamza R.", "meta": "Follows you"},
    {"klass": "c", "initial": "Z", "name": "Zara K.", "meta": "Mutual"},
    {"klass": "f", "initial": "S", "name": "Sana M.", "meta": "Mutual"},
]

TOP_FLAVORS = [
    {"label": "Spicy", "pct": 92, "klass": "k-hot", "bar_klass": "hot"},
    {"label": "Slow-cooked", "pct": 85, "klass": "", "bar_klass": ""},
    {"label": "Beef-forward", "pct": 78, "klass": "", "bar_klass": ""},
    {"label": "Fresh & herby", "pct": 31, "klass": "k-mint", "bar_klass": "veg"},
]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(request, "namak/landing.html", {"hero_dishes": HERO_DISHES})


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding(request: Request):
    picked_count = sum(1 for d in DISH_TILES if d["picked"])
    return templates.TemplateResponse(
        request, "namak/onboarding.html",
        {"dish_tiles": DISH_TILES, "picked_count": picked_count},
    )


@router.get("/feed", response_class=HTMLResponse)
def feed(request: Request):
    return templates.TemplateResponse(
        request, "namak/feed.html",
        {
            "active": "for-you", "search": True, "demo_user": DEMO_USER,
            "hero_pick": HERO_PICK, "picks": PICKS, "similar_picks": SIMILAR_PICKS,
            "taste_twins": TASTE_TWINS, "following_activity": FOLLOWING_ACTIVITY, "trending": TRENDING,
        },
    )


@router.get("/restaurant/{slug}", response_class=HTMLResponse)
def restaurant_detail(request: Request, slug: str):
    r = RESTAURANTS.get(slug, RESTAURANTS["waris-nihari"])
    return templates.TemplateResponse(
        request, "namak/restaurant.html",
        {
            "demo_user": DEMO_USER, "restaurant": r, "dishes": r["dishes"],
            "reviews": r["reviews"], "match": r["match"], "aspects": r["aspects"],
        },
    )


@router.get("/u/{username}", response_class=HTMLResponse)
def profile(request: Request, username: str):
    p = PROFILES.get(username, PROFILES["areeba"])
    return templates.TemplateResponse(
        request, "namak/profile.html",
        {
            "demo_user": DEMO_USER, "profile": p, "collections": COLLECTIONS, "activity": ACTIVITY,
            "twin_overlap": TWIN_OVERLAP, "mutual_followers": MUTUAL_FOLLOWERS, "top_flavors": TOP_FLAVORS,
        },
    )
