import re


def _csrf(response):
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def _login_partner(client, backend, auth_provider, *, role="restaurant_partner"):
    backend.profile = backend.profile.model_copy(update={"role": role})
    backend.restaurant = backend.restaurant.model_copy(
        update={"owner_id": auth_provider.user.id}
    )
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": _csrf(page),
            "email": "test@example.com",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _form(csrf, restaurant_id, creation_key, **overrides):
    values = {
        "csrf_token": csrf,
        "restaurant_id": str(restaurant_id),
        "creation_key": creation_key,
        "name": "Partner Karahi",
        "description": "Tomato-forward chicken karahi",
        "cuisine": "Pakistani",
        "price": "1250",
        "availability": "true",
        "ingredients": "chicken, tomato, ginger",
        "allergens": "dairy",
        "dietary_tags": "high-protein",
        "preparation_style": "stovetop",
        "spice_level": "4",
        "sweetness": "1",
        "sourness": "2",
        "saltiness": "3",
        "oiliness": "3",
        "richness": "4",
        "smokiness": "1",
        "texture_tags": "tender, saucy",
    }
    values.update(overrides)
    return values


def _hidden(response, name):
    match = re.search(rf'name="{name}" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def test_partner_menu_create_view_and_duplicate_submit(
    web_client, backend_client, auth_provider
):
    _login_partner(web_client, backend_client, auth_provider)
    dashboard = web_client.get("/partner/dashboard")
    assert "Manage menu" in dashboard.text
    new = web_client.get(
        f"/partner/restaurants/{backend_client.restaurant.id}/dishes/new"
    )
    key = _hidden(new, "creation_key")
    data = _form(_csrf(new), backend_client.restaurant.id, key)
    first = web_client.post("/partner/dishes", data=data, follow_redirects=False)
    second = web_client.post("/partner/dishes", data=data, follow_redirects=False)
    assert first.status_code == second.status_code == 303
    assert len(backend_client.partner_dish_items) == 1
    dish = backend_client.partner_dish_items[0]
    menu = web_client.get(f"/partner/restaurants/{backend_client.restaurant.id}/menu")
    detail = web_client.get(f"/partner/dishes/{dish.id}")
    assert "Partner Karahi" in menu.text
    assert "384-dimensional" in new.text
    assert "Ingredients and safety" in detail.text


def test_partner_dish_update_availability_and_archive(
    web_client, backend_client, auth_provider
):
    _login_partner(web_client, backend_client, auth_provider)
    new = web_client.get(
        f"/partner/restaurants/{backend_client.restaurant.id}/dishes/new"
    )
    web_client.post(
        "/partner/dishes",
        data=_form(
            _csrf(new),
            backend_client.restaurant.id,
            _hidden(new, "creation_key"),
        ),
    )
    dish = backend_client.partner_dish_items[0]
    edit = web_client.get(f"/partner/dishes/{dish.id}/edit")
    updated = web_client.post(
        f"/partner/dishes/{dish.id}",
        data=_form(
            "",
            backend_client.restaurant.id,
            "",
            csrf_token=_csrf(edit),
            name="Updated Dish",
        ),
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert backend_client.partner_dish_items[0].name == "Updated Dish"
    menu = web_client.get(f"/partner/restaurants/{backend_client.restaurant.id}/menu")
    csrf = _csrf(menu)
    web_client.post(
        f"/partner/dishes/{dish.id}/availability",
        data={"csrf_token": csrf, "available": "false"},
    )
    archived = web_client.post(
        f"/partner/dishes/{dish.id}/archive", data={"csrf_token": csrf}
    )
    assert archived.status_code == 200
    assert backend_client.partner_dish_items[0].archived_at is not None


def test_dish_validation_preserves_values_and_csrf(
    web_client, backend_client, auth_provider
):
    _login_partner(web_client, backend_client, auth_provider)
    new = web_client.get(
        f"/partner/restaurants/{backend_client.restaurant.id}/dishes/new"
    )
    key = _hidden(new, "creation_key")
    invalid = web_client.post(
        "/partner/dishes",
        data=_form(
            _csrf(new),
            backend_client.restaurant.id,
            key,
            name="Remember This Dish",
            price="0",
        ),
    )
    assert invalid.status_code == 422
    assert 'value="Remember This Dish"' in invalid.text
    assert web_client.post("/partner/dishes", data={}).status_code == 403


def test_customer_cannot_access_partner_menu(web_client, backend_client, auth_provider):
    _login_partner(web_client, backend_client, auth_provider, role="customer")
    assert (
        web_client.get(
            f"/partner/restaurants/{backend_client.restaurant.id}/menu"
        ).status_code
        == 403
    )
