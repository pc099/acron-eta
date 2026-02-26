import hashlib

from httpx import AsyncClient

from app.db.models import ApiKey


async def test_no_auth_header_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/orgs/some-org")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "auth_required"


async def test_invalid_auth_header_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        "/orgs/some-org",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "invalid_auth"


async def test_valid_api_key_sets_org_context(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    org = seed_org["org"]  # type: ignore[index]
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    resp = await client.get(
        f"/orgs/{org.slug}", headers={"Authorization": f"Bearer {raw_key}"}  # type: ignore[attr-defined]
    )
    assert resp.status_code == 200


async def test_revoked_api_key_returns_401(
    client: AsyncClient,
    seed_org: dict[str, object],
    session_factory,
) -> None:
    api_key = seed_org["api_key"]  # type: ignore[index]
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    # Revoke the key in the database
    async with session_factory() as session:
        db_key = await session.get(ApiKey, api_key.id)  # type: ignore[attr-defined]
        assert db_key is not None
        db_key.is_active = False
        await session.commit()

    resp = await client.get(
        "/orgs/test-org", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "invalid_api_key"

