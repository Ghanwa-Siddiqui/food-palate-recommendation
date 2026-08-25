"""Onboarding: form UI + submit endpoint."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..models import OnboardingAnswers
from ..personalization import user_from_onboarding
from ..repositories import get_repository

router = APIRouter(tags=["onboarding"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

CUISINE_CHOICES = [
    "Pakistani", "Chinese", "Italian", "Continental", "American",
    "Japanese", "Mexican", "Street", "Cafe",
]
DIETARY_CHOICES = ["halal", "vegetarian", "vegan", "no-beef", "no-pork", "gluten-free"]


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_form(request: Request):
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"cuisines": CUISINE_CHOICES, "dietary": DIETARY_CHOICES},
    )


@router.post("/onboarding")
def submit_onboarding(
    request: Request,
    cuisines: list[str] = Form(default=[]),
    favorite_foods: str = Form(default=""),
    dietary: list[str] = Form(default=[]),
    spice_pref: int = Form(default=2),
    budget: int = Form(default=1000),
):
    answers = OnboardingAnswers(
        cuisines=cuisines,
        favorite_foods=favorite_foods,  # validator splits on commas
        dietary=dietary,
        spice_pref=spice_pref,
        budget=budget,
    )
    user_id = f"u_{uuid.uuid4().hex[:10]}"
    user = user_from_onboarding(user_id, answers)
    get_repository().upsert_user(user)
    return RedirectResponse(url=f"/onboarding/done?user_id={user_id}", status_code=303)


@router.get("/onboarding/done", response_class=HTMLResponse)
def onboarding_done(request: Request, user_id: str):
    user = get_repository().get_user(user_id)
    return templates.TemplateResponse(
        request,
        "onboarding_done.html",
        {"user": user, "user_id": user_id},
    )
