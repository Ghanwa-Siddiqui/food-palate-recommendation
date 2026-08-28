from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import (
    AuthError,
    AuthProvider,
    AuthUser,
    InvalidCredentialsError,
    get_auth_provider,
)
from ..backend_client import (
    BackendError,
    BackendNotFound,
    BackendValidationError,
    ChaskaBackendClient,
    get_backend_client,
)
from ..image_assets import (
    context_image,
    cuisine_image,
    dish_image,
    fallback_image,
    feed_images,
    image_attributions,
    restaurant_image,
)
from ..models import OnboardingAnswers
from ..personalization import build_taste_vector

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


templates.env.globals.update(
    cuisine_image=cuisine_image,
    dish_image=dish_image,
    feed_images=feed_images,
    restaurant_image=restaurant_image,
    context_image=context_image,
    fallback_image=fallback_image,
)

CUISINES = [
    "Pakistani",
    "Chinese",
    "Italian",
    "Turkish",
    "Japanese",
    "Thai",
    "Continental",
    "Fast Food",
]
FAVOURITES = [
    "Biryani",
    "Karahi",
    "Nihari",
    "Pizza",
    "Burger",
    "Pasta",
    "BBQ",
    "Kebab",
    "Sushi",
    "Chow Mein",
    "Dessert",
]
TEXTURES = ["crispy", "tender", "creamy", "chewy", "crunchy", "soft"]
DIETARY = ["vegetarian", "vegan", "gluten-free", "no-beef", "no-pork"]
TASTE_FIELDS = (
    "spice_preference",
    "sweetness_preference",
    "sourness_preference",
    "saltiness_preference",
    "oiliness_preference",
    "richness_preference",
)


def _form_tags(form, *names: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        for raw in form.getlist(name):
            for item in str(raw).split(","):
                clean = item.strip()
                normalized = clean.casefold()
                if clean and normalized not in seen:
                    result.append(clean)
                    seen.add(normalized)
    return result


def _quiz_context(request: Request, user, **context):
    return _base(
        request,
        user,
        cuisines=CUISINES,
        favourites=FAVOURITES,
        textures=TEXTURES,
        dietary=DIETARY,
        **context,
    )


def _csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf_token"] = token
    return token


def _valid_csrf(request: Request, value: str | None) -> bool:
    expected = request.session.get("csrf_token", "")
    return bool(value and expected and secrets.compare_digest(value, expected))


def _store_session(request: Request, session) -> None:
    request.session["auth"] = {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


def _current_user(request: Request, provider: AuthProvider) -> AuthUser | None:
    state = request.session.get("auth")
    if not state:
        return None
    try:
        return provider.verify(state["access_token"])
    except InvalidCredentialsError:
        try:
            refreshed = provider.refresh(state["refresh_token"])
        except InvalidCredentialsError:
            request.session.clear()
            return None
        _store_session(request, refreshed)
        return refreshed.user


def _login_redirect(request: Request) -> RedirectResponse:
    next_path = request.url.path
    return RedirectResponse(
        f"/login?{urlencode({'next': next_path, 'expired': '1'})}", 303
    )


def _base(request: Request, user: AuthUser | None = None, **context):
    return {"user": user, "csrf_token": _csrf(request), **context}


def _require_partner(user: AuthUser, backend: ChaskaBackendClient):
    try:
        profile = backend.get_profile(user.id)
    except BackendError as exc:
        raise HTTPException(
            status_code=503, detail="Partner profile unavailable"
        ) from exc
    if profile.role not in {"restaurant_partner", "admin"}:
        raise HTTPException(
            status_code=403, detail="Restaurant partner access required"
        )
    return profile


def _partner_payload(form) -> dict:
    lat_raw = str(form.get("lat", "")).strip()
    lng_raw = str(form.get("lng", "")).strip()
    if bool(lat_raw) != bool(lng_raw):
        raise ValueError("Latitude and longitude must be supplied together.")
    cuisines = [
        item.strip()
        for item in str(form.get("cuisine_types", "")).split(",")
        if item.strip()
    ]
    if not cuisines:
        raise ValueError("Add at least one cuisine.")
    payload = {
        "name": str(form.get("name", "")).strip(),
        "description": str(form.get("description", "")).strip() or None,
        "address": str(form.get("address", "")).strip(),
        "city": str(form.get("city", "")).strip(),
        "cuisine_types": cuisines,
        "contact_phone": str(form.get("contact_phone", "")).strip() or None,
        "halal_status": str(form.get("halal_status", "unknown")),
        "halal_verification_status": str(
            form.get("halal_verification_status", "unverified")
        ),
        "lat": float(lat_raw) if lat_raw else None,
        "lng": float(lng_raw) if lng_raw else None,
        "opening_information": str(form.get("opening_information", "")).strip() or None,
        "available": form.get("available") == "true",
        "image_path": "/static/images/restaurant-warm-interior.webp",
        "price_range": str(form.get("price_range", "moderate")).strip() or "moderate",
    }
    if (
        len(payload["name"]) < 2
        or len(payload["address"]) < 3
        or len(payload["city"]) < 2
    ):
        raise ValueError("Restaurant name, address and city are required.")
    return payload


def _partner_dish_payload(form, *, include_restaurant: bool) -> dict:
    def tags(name: str) -> list[str]:
        return _form_tags(form, name)

    payload = {
        "name": str(form.get("name", "")).strip(),
        "description": str(form.get("description", "")).strip() or None,
        "cuisine": str(form.get("cuisine", "")).strip(),
        "price": float(form.get("price", 0)),
        "availability": form.get("availability") == "true",
        "ingredients": tags("ingredients"),
        "allergens": tags("allergens"),
        "dietary_tags": tags("dietary_tags"),
        "preparation_style": str(form.get("preparation_style", "")).strip(),
        "image_path": "/static/images/neutral-food-fallback.webp",
        "texture_tags": tags("texture_tags"),
    }
    for field in (
        "spice_level",
        "sweetness",
        "sourness",
        "saltiness",
        "oiliness",
        "richness",
        "smokiness",
    ):
        payload[field] = int(form.get(field, 2))
    if include_restaurant:
        payload["restaurant_id"] = str(form.get("restaurant_id", ""))
    if (
        len(payload["name"]) < 2
        or len(payload["cuisine"]) < 2
        or payload["price"] <= 0
        or not payload["ingredients"]
        or not payload["texture_tags"]
        or len(payload["preparation_style"]) < 2
        or any(not 0 <= payload[field] <= 5 for field in _DISH_TASTE_FIELDS)
    ):
        raise ValueError(
            "Complete the dish name, cuisine, positive price, ingredients, "
            "textures, preparation style and taste levels."
        )
    return payload


_DISH_TASTE_FIELDS = (
    "spice_level",
    "sweetness",
    "sourness",
    "saltiness",
    "oiliness",
    "richness",
    "smokiness",
)


@router.get("/", response_class=HTMLResponse)
def landing(
    request: Request, auth: Annotated[AuthProvider, Depends(get_auth_provider)]
):
    return templates.TemplateResponse(
        request, "namak/landing.html", _base(request, _current_user(request, auth))
    )


@router.get("/credits", response_class=HTMLResponse)
def credits(
    request: Request, auth: Annotated[AuthProvider, Depends(get_auth_provider)]
):
    """Photo attribution. CC BY and CC BY-SA both require visible credit, so
    this is built from the manifest rather than hand-maintained - a newly
    added photograph appears here automatically."""
    return templates.TemplateResponse(
        request,
        "namak/credits.html",
        _base(
            request,
            _current_user(request, auth),
            attributions=image_attributions(),
        ),
    )


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(
        request,
        "namak/auth.html",
        _base(request, mode="signup", error=None, notice=None),
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(
                request,
                mode="signup",
                error="Your form expired. Please try again.",
                notice=None,
            ),
            status_code=403,
        )
    name, email, password = (
        str(form.get("name", "")).strip(),
        str(form.get("email", "")).strip(),
        str(form.get("password", "")),
    )
    role = str(form.get("account_type", "customer"))
    if role not in {"customer", "restaurant_partner"}:
        role = "customer"
    if len(name) < 2 or "@" not in email or len(password) < 8:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(
                request,
                mode="signup",
                error="Enter a name, valid email, and password of at least 8 characters.",
                notice=None,
            ),
            status_code=422,
        )
    try:
        result = auth.signup(email, password, name, role)
    except AuthError as exc:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(request, mode="signup", error=exc.public_message, notice=None),
            status_code=exc.http_status,
        )
    try:
        backend.sync_user(result.user.id, result.user.name, result.user.email, role)
    except BackendError:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(
                request,
                mode="login",
                error=(
                    "Your account was created, but profile setup is temporarily "
                    "unavailable. Log in to retry."
                ),
                notice="Do not create the account again.",
                next=(
                    "/partner/onboarding"
                    if role == "restaurant_partner"
                    else "/onboarding/1"
                ),
            ),
            status_code=503,
        )
    if result.session is None:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(
                request,
                mode="signup",
                error=None,
                notice="Check your email to verify your account, then log in.",
            ),
        )
    _store_session(request, result.session)
    return RedirectResponse(
        "/partner/onboarding" if role == "restaurant_partner" else "/onboarding/1",
        303,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    notice = (
        "Your session expired. Please log in again."
        if request.query_params.get("expired")
        else None
    )
    return templates.TemplateResponse(
        request,
        "namak/auth.html",
        _base(
            request,
            mode="login",
            error=None,
            notice=notice,
            next=request.query_params.get("next", "/app/feed"),
        ),
    )


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(
                request,
                mode="login",
                error="Your form expired. Please try again.",
                notice=None,
            ),
            status_code=403,
        )
    try:
        session = auth.login(
            str(form.get("email", "")).strip(), str(form.get("password", ""))
        )
    except InvalidCredentialsError as exc:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(request, mode="login", error=exc.public_message, notice=None),
            status_code=401,
        )
    except AuthError as exc:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(request, mode="login", error=exc.public_message, notice=None),
            status_code=exc.http_status,
        )
    try:
        backend.sync_user(session.user.id, session.user.name, session.user.email)
        profile = backend.get_profile(session.user.id)
    except BackendError:
        return templates.TemplateResponse(
            request,
            "namak/auth.html",
            _base(
                request,
                mode="login",
                error=(
                    "You signed in, but profile setup is temporarily unavailable. "
                    "Log in again to retry."
                ),
                notice=None,
            ),
            status_code=503,
        )
    _store_session(request, session)
    destination = str(form.get("next", "/app/feed"))
    if not destination.startswith("/app"):
        destination = "/app/feed"
    if profile.role == "restaurant_partner":
        destination = "/partner/dashboard"
    elif not profile.onboarding_complete:
        destination = "/onboarding/1"
    return RedirectResponse(destination, 303)


@router.post("/logout")
async def logout(
    request: Request, auth: Annotated[AuthProvider, Depends(get_auth_provider)]
):
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return RedirectResponse("/app/profile?error=csrf", 303)
    state = request.session.get("auth")
    if state:
        auth.logout(state["access_token"], state["refresh_token"])
    request.session.clear()
    return RedirectResponse("/login?logged_out=1", 303)


@router.get("/onboarding/{step}", response_class=HTMLResponse)
def onboarding_step(
    request: Request,
    step: int,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    if step not in range(1, 6):
        return RedirectResponse("/onboarding/1", 303)
    return templates.TemplateResponse(
        request,
        "namak/onboarding_flow.html",
        _quiz_context(
            request,
            user,
            step=step,
            draft=request.session.get("onboarding", {}),
            error=None,
        ),
    )


@router.post("/onboarding/{step}", response_class=HTMLResponse)
async def onboarding_submit(
    request: Request,
    step: int,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    if step not in range(1, 6):
        return RedirectResponse("/onboarding/1", 303)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return RedirectResponse(f"/onboarding/{step}?error=expired", 303)
    if form.get("direction") == "back":
        return RedirectResponse(f"/onboarding/{max(1, step - 1)}", 303)
    draft = dict(request.session.get("onboarding", {}))
    if step == 1:
        cuisines, city = (
            form.getlist("preferred_cuisines"),
            str(form.get("city", "")).strip(),
        )
        draft.update(preferred_cuisines=cuisines, city=city)
        if not cuisines or not city:
            return templates.TemplateResponse(
                request,
                "namak/onboarding_flow.html",
                _quiz_context(
                    request,
                    user,
                    step=step,
                    draft=draft,
                    error="Choose at least one cuisine and your city.",
                ),
                status_code=422,
            )
    elif step == 2:
        favourites = _form_tags(
            form,
            "favourite_dishes",
            "favourite_dishes_text",
            "favourite_dishes_suggestions",
        )
        if len(favourites) < 3:
            draft["favourite_dishes"] = favourites
            return templates.TemplateResponse(
                request,
                "namak/onboarding_flow.html",
                _quiz_context(
                    request,
                    user,
                    step=step,
                    draft=draft,
                    error="Choose at least three foods.",
                ),
                status_code=422,
            )
        draft["favourite_dishes"] = favourites
    elif step == 3:
        try:
            levels = {name: int(form.get(name, 2)) for name in TASTE_FIELDS}
            if any(value not in range(6) for value in levels.values()):
                raise ValueError
        except (TypeError, ValueError):
            return templates.TemplateResponse(
                request,
                "namak/onboarding_flow.html",
                _quiz_context(
                    request,
                    user,
                    step=step,
                    draft={**draft, **levels} if "levels" in locals() else draft,
                    error="Choose a flavour level from 0 to 5 for every taste.",
                ),
                status_code=422,
            )
        draft.update(levels)
    elif step == 4:
        draft.update(
            preferred_textures=form.getlist("preferred_textures"),
            dietary_requirements=form.getlist("dietary_requirements"),
            allergies=_form_tags(form, "allergies", "allergies_text"),
            disliked_ingredients=_form_tags(
                form, "disliked_ingredients", "disliked_ingredients_text"
            ),
            require_halal=form.get("require_halal") == "true",
        )
    elif step == 5:
        try:
            budget_min = float(form.get("budget_min", 0))
            budget_max = float(form.get("budget_max", 1500))
            draft.update(budget_min=budget_min, budget_max=budget_max)
            if budget_min < 0 or budget_max < budget_min:
                raise ValueError
            answers = OnboardingAnswers.model_validate(draft)
            payload = answers.model_dump()
            payload["taste_vector"] = build_taste_vector(answers)
            backend.update_profile(user.id, payload)
        except (ValueError, BackendError):
            return templates.TemplateResponse(
                request,
                "namak/onboarding_flow.html",
                _quiz_context(
                    request,
                    user,
                    step=step,
                    draft=draft,
                    error=(
                        "Check that your minimum budget does not exceed your maximum, "
                        "then try again."
                    ),
                ),
                status_code=422,
            )
        request.session.pop("onboarding", None)
        return templates.TemplateResponse(
            request,
            "namak/onboarding_complete.html",
            _base(request, user),
        )
    request.session["onboarding"] = draft
    return RedirectResponse(f"/onboarding/{step + 1}", 303)


def _feed_params(request: Request) -> list[tuple[str, str]]:
    allowed = (
        "search",
        "budget_min",
        "budget_max",
        "max_distance_km",
        "user_lat",
        "user_lng",
        "offset",
    )
    params = [
        (name, request.query_params[name])
        for name in allowed
        if request.query_params.get(name)
    ]
    if request.query_params.get("require_halal") == "true":
        params.append(("require_halal", "true"))
    for value in request.query_params.getlist("dietary_restrictions"):
        params.append(("dietary_restrictions", value))
    params.append(("limit", "12"))
    return params


def _feed_filter_errors(request: Request) -> list[str]:
    errors: list[str] = []

    def number(name: str, label: str, *, minimum: float | None = None) -> float | None:
        raw = request.query_params.get(name, "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            errors.append(f"{label} must be a number.")
            return None
        if minimum is not None and value < minimum:
            errors.append(f"{label} must be at least {minimum:g}.")
        return value

    budget_min = number("budget_min", "Minimum budget", minimum=0)
    budget_max = number("budget_max", "Maximum budget", minimum=1)
    distance = number("max_distance_km", "Maximum distance", minimum=0.1)
    latitude = number("user_lat", "Latitude")
    longitude = number("user_lng", "Longitude")
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        errors.append("Minimum budget cannot exceed maximum budget.")
    if (latitude is None) != (longitude is None):
        errors.append("Latitude and longitude must be supplied together.")
    if latitude is not None and not -90 <= latitude <= 90:
        errors.append("Latitude must be between -90 and 90.")
    if longitude is not None and not -180 <= longitude <= 180:
        errors.append("Longitude must be between -180 and 180.")
    if distance is not None and (latitude is None or longitude is None):
        errors.append("Maximum distance requires valid coordinates.")
    return errors


@router.get("/app/feed", response_class=HTMLResponse)
def feed(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    try:
        profile = backend.get_profile(user.id)
        if not profile.onboarding_complete:
            return RedirectResponse("/onboarding/1", 303)
        filter_errors = _feed_filter_errors(request)
        if filter_errors:
            result, twins, state = None, [], "validation"
        else:
            result = backend.get_feed(user.id, _feed_params(request))
            twins = backend.similar_users(user.id)
            state = "success" if result.items else "empty"
    except BackendNotFound:
        return RedirectResponse("/onboarding/1", 303)
    except BackendError:
        profile, result, twins, state, filter_errors = None, None, [], "error", []
    return templates.TemplateResponse(
        request,
        "namak/feed.html",
        _base(
            request,
            user,
            profile=profile,
            feed=result,
            twins=twins,
            state=state,
            filter_errors=filter_errors,
            filters=request.query_params,
            event_id=secrets.token_urlsafe(16),
            welcome=request.query_params.get("welcome"),
        ),
    )


@router.post("/app/interactions")
async def interaction(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    form = await request.form()
    destination = str(form.get("next", "/app/feed"))
    if not destination.startswith("/app"):
        destination = "/app/feed"
    if not _valid_csrf(request, form.get("csrf_token")):
        return RedirectResponse(f"{destination}?action_error=expired", 303)
    try:
        dish_id = UUID(str(form.get("dish_id")))
        action = str(form.get("action"))
        if action == "unsave":
            backend.unsave(user.id, dish_id)
        elif action in {"click", "save", "order", "tried", "like", "dislike"}:
            backend.interact(user.id, dish_id, action, str(form.get("event_id")))
        else:
            raise ValueError
    except (ValueError, BackendError):
        return RedirectResponse(f"{destination}?action_error=1", 303)
    return RedirectResponse(f"{destination}?action={action}", 303)


@router.get("/app/restaurants/{restaurant_id}", response_class=HTMLResponse)
def restaurant_detail(
    request: Request,
    restaurant_id: UUID,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    try:
        restaurant = backend.get_restaurant(restaurant_id)
        ranked = backend.get_feed(
            user.id, [("restaurant_id", str(restaurant_id)), ("limit", "100")]
        )
        deals = backend.restaurant_deals(restaurant_id)
        summaries = {
            item.dish_id: backend.review_summary(item.dish_id) for item in ranked.items
        }
    except BackendNotFound:
        return templates.TemplateResponse(
            request,
            "namak/not_found.html",
            _base(request, user, title="Restaurant not found"),
            status_code=404,
        )
    except BackendError:
        return templates.TemplateResponse(
            request,
            "namak/not_found.html",
            _base(request, user, title="Restaurant data is unavailable"),
            status_code=503,
        )
    return templates.TemplateResponse(
        request,
        "namak/restaurant.html",
        _base(
            request,
            user,
            restaurant=restaurant,
            dishes=ranked.items,
            deals=deals,
            summaries=summaries,
            event_id=secrets.token_urlsafe(16),
        ),
    )


@router.get("/app/dishes/{dish_id}", response_class=HTMLResponse)
def dish_detail(
    request: Request,
    dish_id: UUID,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    try:
        dish = backend.get_dish(dish_id)
        restaurant = backend.get_restaurant(dish.restaurant_id)
        summary = backend.review_summary(dish_id)
        reviews = backend.dish_reviews(dish_id)
        own_review = backend.my_review(user.id, dish_id)
        profile = backend.get_profile(user.id)
        selected_actions = {
            item.action
            for item in backend.interactions(user.id)
            if item.dish_id == dish_id
        }
        ranked = backend.get_feed(
            user.id, [("restaurant_id", str(dish.restaurant_id)), ("limit", "100")]
        )
        match = next((item for item in ranked.items if item.dish_id == dish_id), None)
    except BackendNotFound:
        return templates.TemplateResponse(
            request,
            "namak/not_found.html",
            _base(request, user, title="Dish not found"),
            status_code=404,
        )
    except BackendError:
        return templates.TemplateResponse(
            request,
            "namak/not_found.html",
            _base(request, user, title="Dish data is unavailable"),
            status_code=503,
        )
    return templates.TemplateResponse(
        request,
        "namak/dish.html",
        _base(
            request,
            user,
            dish=dish,
            restaurant=restaurant,
            summary=summary,
            reviews=reviews,
            own_review=own_review,
            customer=profile.role == "customer",
            review_error=request.query_params.get("review_error"),
            review_success=request.query_params.get("review") == "saved",
            review_draft=request.session.pop("dish_review_draft", None),
            selected_actions=selected_actions,
            match=match,
            event_id=secrets.token_urlsafe(16),
        ),
    )


@router.post("/app/dishes/{dish_id}/reviews", response_class=HTMLResponse)
async def submit_review(
    request: Request,
    dish_id: UUID,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    try:
        tried = form.get("tried_confirmation") == "on"
        if tried:
            backend.interact(user.id, dish_id, "tried", str(form.get("tried_event_id")))
        payload = {
            "rating": int(str(form.get("rating"))),
            "text": str(form.get("text", "")),
            "show_display_name": form.get("show_display_name") == "on",
        }
        review_id = form.get("review_id")
        if review_id:
            backend.update_review(user.id, UUID(str(review_id)), payload)
        else:
            backend.create_review(
                user.id,
                {
                    **payload,
                    "dish_id": str(dish_id),
                    "tried_confirmation": tried,
                    "submission_key": str(form.get("submission_key")),
                },
            )
    except (ValueError, BackendValidationError):
        request.session["dish_review_draft"] = {
            "rating": str(form.get("rating", "")),
            "text": str(form.get("text", "")),
            "tried_confirmation": form.get("tried_confirmation") == "on",
            "show_display_name": form.get("show_display_name") == "on",
        }
        return RedirectResponse(f"/app/dishes/{dish_id}?review_error=validation", 303)
    except BackendError:
        request.session["dish_review_draft"] = {
            "rating": str(form.get("rating", "")),
            "text": str(form.get("text", "")),
            "tried_confirmation": form.get("tried_confirmation") == "on",
            "show_display_name": form.get("show_display_name") == "on",
        }
        return RedirectResponse(f"/app/dishes/{dish_id}?review_error=unavailable", 303)
    return RedirectResponse(f"/app/dishes/{dish_id}?review=saved", 303)


@router.get("/app/saved", response_class=HTMLResponse)
def saved(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    try:
        saved_ids = list(
            dict.fromkeys(
                item.dish_id
                for item in backend.interactions(user.id)
                if item.action == "save"
            )
        )
        dishes = [backend.get_dish(dish_id) for dish_id in saved_ids]
    except BackendError:
        dishes = None
    return templates.TemplateResponse(
        request,
        "namak/saved.html",
        _base(request, user, dishes=dishes, event_id=secrets.token_urlsafe(16)),
    )


@router.get("/app/profile", response_class=HTMLResponse)
def profile(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    try:
        profile_data = backend.get_profile(user.id)
        activity = backend.interactions(user.id)
        twins = backend.similar_users(user.id)
    except BackendError:
        profile_data, activity, twins = None, None, []
    return templates.TemplateResponse(
        request,
        "namak/profile.html",
        _base(request, user, profile=profile_data, activity=activity, twins=twins),
    )


@router.get("/partner/onboarding", response_class=HTMLResponse)
def partner_onboarding(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    return templates.TemplateResponse(
        request,
        "namak/partner_restaurant_form.html",
        _base(request, user, restaurant=None, onboarding=True, error=None),
    )


@router.post("/partner/restaurants", response_class=HTMLResponse)
async def partner_create_restaurant(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    try:
        payload = _partner_payload(form)
        backend.create_partner_restaurant(user.id, payload)
    except (ValueError, BackendValidationError) as exc:
        message = (
            str(exc) if isinstance(exc, ValueError) else "Check the restaurant details."
        )
        return templates.TemplateResponse(
            request,
            "namak/partner_restaurant_form.html",
            _base(request, user, restaurant=dict(form), onboarding=True, error=message),
            status_code=422,
        )
    return RedirectResponse("/partner/dashboard?created=1", 303)


@router.get("/partner/dashboard", response_class=HTMLResponse)
def partner_dashboard(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    profile_data = _require_partner(user, backend)
    restaurants = backend.partner_restaurants(user.id)
    return templates.TemplateResponse(
        request,
        "namak/partner_dashboard.html",
        _base(
            request,
            user,
            profile=profile_data,
            restaurants=restaurants,
            created=request.query_params.get("created") == "1",
            saved=request.query_params.get("saved") == "1",
        ),
    )


@router.get("/partner/restaurants/{restaurant_id}/edit", response_class=HTMLResponse)
def partner_edit_restaurant(
    restaurant_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Restaurant ownership check failed")
    return templates.TemplateResponse(
        request,
        "namak/partner_restaurant_form.html",
        _base(
            request,
            user,
            restaurant=owned[restaurant_id].model_dump(),
            onboarding=False,
            error=None,
        ),
    )


@router.post("/partner/restaurants/{restaurant_id}", response_class=HTMLResponse)
async def partner_update_restaurant(
    restaurant_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    try:
        payload = _partner_payload(form)
        backend.update_partner_restaurant(user.id, restaurant_id, payload)
    except (ValueError, BackendValidationError) as exc:
        message = (
            str(exc) if isinstance(exc, ValueError) else "Check the restaurant details."
        )
        return templates.TemplateResponse(
            request,
            "namak/partner_restaurant_form.html",
            _base(
                request, user, restaurant=dict(form), onboarding=False, error=message
            ),
            status_code=422,
        )
    return RedirectResponse("/partner/dashboard?saved=1", 303)


@router.get("/partner/restaurants/{restaurant_id}/menu", response_class=HTMLResponse)
def partner_menu(
    restaurant_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Restaurant ownership check failed")
    dishes = backend.partner_menu(user.id, restaurant_id)
    return templates.TemplateResponse(
        request,
        "namak/partner_menu.html",
        _base(
            request,
            user,
            restaurant=owned[restaurant_id],
            dishes=dishes,
            created=request.query_params.get("created") == "1",
            saved=request.query_params.get("saved") == "1",
        ),
    )


@router.get(
    "/partner/restaurants/{restaurant_id}/dishes/new", response_class=HTMLResponse
)
def partner_new_dish(
    restaurant_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Restaurant ownership check failed")
    creation_key = secrets.token_urlsafe(24)
    keys = request.session.setdefault("partner_dish_creation_keys", [])
    keys.append(creation_key)
    request.session["partner_dish_creation_keys"] = keys[-10:]
    return templates.TemplateResponse(
        request,
        "namak/partner_dish_form.html",
        _base(
            request,
            user,
            restaurant=owned[restaurant_id],
            dish=None,
            creation_key=creation_key,
            error=None,
        ),
    )


@router.post("/partner/dishes", response_class=HTMLResponse)
async def partner_create_dish(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    creation_key = str(form.get("creation_key", ""))
    if creation_key not in request.session.get("partner_dish_creation_keys", []):
        raise HTTPException(status_code=409, detail="Dish form token is invalid")
    try:
        restaurant_id = UUID(str(form.get("restaurant_id", "")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid restaurant") from exc
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Restaurant ownership check failed")
    try:
        payload = _partner_dish_payload(form, include_restaurant=True)
        backend.create_partner_dish(user.id, payload, creation_key)
    except (ValueError, BackendValidationError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Check the dish profile."
        return templates.TemplateResponse(
            request,
            "namak/partner_dish_form.html",
            _base(
                request,
                user,
                restaurant=owned[restaurant_id],
                dish=dict(form),
                creation_key=creation_key,
                error=message,
            ),
            status_code=422,
        )
    return RedirectResponse(f"/partner/restaurants/{restaurant_id}/menu?created=1", 303)


@router.get("/partner/dishes/{dish_id}", response_class=HTMLResponse)
def partner_dish_detail(
    dish_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    dish = backend.partner_dish(user.id, dish_id)
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if dish.restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Dish ownership check failed")
    reviews = backend.dish_reviews(dish_id)
    summary = backend.review_summary(dish_id)
    return templates.TemplateResponse(
        request,
        "namak/partner_dish_detail.html",
        _base(
            request,
            user,
            dish=dish,
            restaurant=owned[dish.restaurant_id],
            reviews=reviews,
            summary=summary,
        ),
    )


@router.get("/partner/dishes/{dish_id}/edit", response_class=HTMLResponse)
def partner_edit_dish(
    dish_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    dish = backend.partner_dish(user.id, dish_id)
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if dish.restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Dish ownership check failed")
    return templates.TemplateResponse(
        request,
        "namak/partner_dish_form.html",
        _base(
            request,
            user,
            restaurant=owned[dish.restaurant_id],
            dish=dish.model_dump(),
            creation_key=None,
            error=None,
        ),
    )


@router.post("/partner/dishes/{dish_id}", response_class=HTMLResponse)
async def partner_update_dish(
    dish_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    current = backend.partner_dish(user.id, dish_id)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    owned = {item.id: item for item in backend.partner_restaurants(user.id)}
    if current.restaurant_id not in owned:
        raise HTTPException(status_code=403, detail="Dish ownership check failed")
    try:
        payload = _partner_dish_payload(form, include_restaurant=False)
        backend.update_partner_dish(user.id, dish_id, payload)
    except (ValueError, BackendValidationError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Check the dish profile."
        values = dict(form)
        values["id"] = str(dish_id)
        return templates.TemplateResponse(
            request,
            "namak/partner_dish_form.html",
            _base(
                request,
                user,
                restaurant=owned[current.restaurant_id],
                dish=values,
                creation_key=None,
                error=message,
            ),
            status_code=422,
        )
    return RedirectResponse(
        f"/partner/restaurants/{current.restaurant_id}/menu?saved=1", 303
    )


@router.post("/partner/dishes/{dish_id}/availability")
async def partner_dish_availability(
    dish_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    dish = backend.partner_dish(user.id, dish_id)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    backend.set_partner_dish_availability(
        user.id, dish_id, form.get("available") == "true"
    )
    return RedirectResponse(f"/partner/restaurants/{dish.restaurant_id}/menu", 303)


@router.post("/partner/dishes/{dish_id}/archive")
async def partner_archive_dish(
    dish_id: UUID,
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    _require_partner(user, backend)
    dish = backend.partner_dish(user.id, dish_id)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    backend.archive_partner_dish(user.id, dish_id)
    return RedirectResponse(f"/partner/restaurants/{dish.restaurant_id}/menu", 303)


@router.get("/app/preferences", response_class=HTMLResponse)
def preferences(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    try:
        profile_data = backend.get_profile(user.id)
    except BackendError:
        profile_data = None
    return templates.TemplateResponse(
        request,
        "namak/preferences.html",
        _quiz_context(
            request,
            user,
            profile=profile_data,
            values=profile_data.model_dump() if profile_data else None,
            error=None,
            saved=request.query_params.get("saved") == "1",
        ),
    )


@router.post("/app/preferences", response_class=HTMLResponse)
async def update_preferences(
    request: Request,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    backend: Annotated[ChaskaBackendClient, Depends(get_backend_client)],
):
    user = _current_user(request, auth)
    if user is None:
        return _login_redirect(request)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return RedirectResponse("/app/preferences?error=expired", 303)
    try:
        current = backend.get_profile(user.id)
    except BackendError:
        return templates.TemplateResponse(
            request,
            "namak/preferences.html",
            _quiz_context(
                request,
                user,
                profile=None,
                values=None,
                error="Preferences are temporarily unavailable.",
                saved=False,
            ),
            status_code=503,
        )
    values = {
        "city": str(form.get("city", "")).strip(),
        "preferred_cuisines": form.getlist("preferred_cuisines"),
        "favourite_dishes": _form_tags(
            form,
            "favourite_dishes",
            "favourite_dishes_text",
            "favourite_dishes_suggestions",
        ),
        "preferred_textures": form.getlist("preferred_textures"),
        "dietary_requirements": form.getlist("dietary_requirements"),
        "allergies": _form_tags(form, "allergies", "allergies_text"),
        "disliked_ingredients": _form_tags(
            form, "disliked_ingredients", "disliked_ingredients_text"
        ),
        "require_halal": form.get("require_halal") == "true",
    }
    try:
        values.update(
            budget_min=float(form.get("budget_min", current.budget_min)),
            budget_max=float(form.get("budget_max", current.budget_max)),
            **{
                name: int(form.get(name, getattr(current, name)))
                for name in TASTE_FIELDS
            },
        )
        if (
            not values["city"]
            or not values["preferred_cuisines"]
            or values["budget_min"] < 0
            or values["budget_max"] < values["budget_min"]
        ):
            raise ValueError
        answers = OnboardingAnswers.model_validate(values)
        payload = answers.model_dump()
        payload["taste_vector"] = build_taste_vector(answers)
        backend.update_profile(user.id, payload)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "namak/preferences.html",
            _quiz_context(
                request,
                user,
                profile=current,
                values=values,
                error=(
                    "Check your location, cuisines, flavour levels and budget range. "
                    "Your selections are still here."
                ),
                saved=False,
            ),
            status_code=422,
        )
    except BackendError:
        return templates.TemplateResponse(
            request,
            "namak/preferences.html",
            _quiz_context(
                request,
                user,
                profile=current,
                values=values,
                error="We could not save just now. Your selections are still here.",
                saved=False,
            ),
            status_code=503,
        )
    return RedirectResponse("/app/preferences?saved=1", 303)
