from httpx import AsyncClient


async def test_get_org_by_slug(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    org = seed_org["org"]  # type: ignore[index]
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    resp = await client.get(f"/orgs/{org.slug}", headers={"Authorization": f"Bearer {raw_key}"})  # type: ignore[attr-defined]
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == org.slug  # type: ignore[attr-defined]


async def test_list_members(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    org = seed_org["org"]  # type: ignore[index]
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    resp = await client.get(
        f"/orgs/{org.slug}/members",
        headers={"Authorization": f"Bearer {raw_key}"},  # type: ignore[attr-defined]
    )
    assert resp.status_code == 200
    members = resp.json()
    assert isinstance(members, list)
    assert members


async def test_usage_endpoint(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    org = seed_org["org"]  # type: ignore[index]
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    resp = await client.get(
        f"/orgs/{org.slug}/usage",
        headers={"Authorization": f"Bearer {raw_key}"},  # type: ignore[attr-defined]
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_requests" in data
    assert "monthly_request_limit" in data
    assert "monthly_token_limit" in data

