"""Onboarding: form UI + submit endpoint."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..models import OnboardingAnswers
from ..personalization import user_from_onboarding
from ..ranking_sync import mirror_demo_user
from ..repositories import get_repository

router = APIRouter(tags=["onboarding"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

CUISINE_CHOICES = [
    "Pakistani", "Chinese", "Italian", "Continental", "American",
    "Japanese", "Mexican", "Street", "Cafe",
]
DIETARY_CHOICES = ["halal", "vegetarian", "vegan", "no-beef", "no-pork", "gluten-free"]
TEXTURE_CHOICES = ["crispy", "tender", "creamy", "chewy", "gelatinous", "crunchy"]


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_form(request: Request):
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"cuisines": CUISINE_CHOICES, "dietary": DIETARY_CHOICES, "textures": TEXTURE_CHOICES},
    )


@router.post("/onboarding")
def submit_onboarding(
    request: Request,
    cuisines: list[str] = Form(default=[]),
    favourite_dishes: str = Form(default=""),
    dietary: list[str] = Form(default=[]),
    textures: list[str] = Form(default=[]),
    allergies: str = Form(default=""),
    disliked_ingredients: str = Form(default=""),
    spice_preference: int = Form(default=2),
    sweetness_preference: int = Form(default=2),
    sourness_preference: int = Form(default=2),
    saltiness_preference: int = Form(default=2),
    oiliness_preference: int = Form(default=2),
    budget_min: float = Form(default=0),
    budget_max: float = Form(default=1500),
):
    answers = OnboardingAnswers(
        preferred_cuisines=cuisines,
        favourite_dishes=favourite_dishes,  # validator splits on commas
        dietary_requirements=dietary,
        preferred_textures=textures,
        allergies=allergies,
        disliked_ingredients=disliked_ingredients,
        spice_preference=spice_preference,
        sweetness_preference=sweetness_preference,
        sourness_preference=sourness_preference,
        saltiness_preference=saltiness_preference,
        oiliness_preference=oiliness_preference,
        budget_min=budget_min,
        budget_max=budget_max,
    )
    user_id = str(uuid.uuid4())
    user = user_from_onboarding(user_id, answers)
    get_repository().upsert_user(user)
    mirror_demo_user(user_id)
    return RedirectResponse(url=f"/onboarding/done?user_id={user_id}", status_code=303)


@router.get("/onboarding/done", response_class=HTMLResponse)
def onboarding_done(request: Request, user_id: str):
    user = get_repository().get_user(user_id)
    return templates.TemplateResponse(
        request,
        "onboarding_done.html",
        {"user": user, "user_id": user_id},
    )
