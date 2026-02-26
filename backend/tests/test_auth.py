from httpx import AsyncClient


async def test_signup_creates_user_and_org(client: AsyncClient) -> None:
    body = {
        "email": "newuser@example.com",
        "name": "New User",
        "clerk_user_id": "clerk_new",
        "org_name": "New Org",
    }
    response = await client.post("/auth/signup", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == body["email"]
    assert data["org_slug"]
    assert data["org_id"]


async def test_signup_duplicate_email_returns_409(client: AsyncClient) -> None:
    body = {
        "email": "dupe@example.com",
        "name": "Dupe User",
        "clerk_user_id": "clerk_dupe_1",
    }
    first = await client.post("/auth/signup", json=body)
    assert first.status_code == 200

    second = await client.post("/auth/signup", json=body)
    assert second.status_code == 409


async def test_login_with_valid_clerk_user_id_returns_orgs(client: AsyncClient) -> None:
    signup_body = {
        "email": "login@example.com",
        "name": "Login User",
        "clerk_user_id": "clerk_login",
        "org_name": "Login Org",
    }
    signup_resp = await client.post("/auth/signup", json=signup_body)
    assert signup_resp.status_code == 200

    login_resp = await client.post(
        "/auth/login", json={"clerk_user_id": "clerk_login"}
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["email"] == signup_body["email"]
    assert isinstance(data["organisations"], list)
    assert len(data["organisations"]) >= 1


async def test_login_unknown_clerk_user_id_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login", json={"clerk_user_id": "nonexistent_clerk_id"}
    )
    assert resp.status_code == 404

