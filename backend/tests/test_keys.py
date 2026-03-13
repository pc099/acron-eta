import uuid

from httpx import AsyncClient


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_keys_crud_lifecycle(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    list_resp = await client.get("/keys", headers=_auth_header(raw_key))
    assert list_resp.status_code == 200
    keys = list_resp.json()
    assert isinstance(keys, list)
    assert keys
    existing_id = keys[0]["id"]
    assert "raw_key" not in keys[0]
    assert "key_hash" not in keys[0]

    create_body = {
        "name": "Created via tests",
        "environment": "live",
        "scopes": ["*"],
    }
    create_resp = await client.post(
        "/keys", json=create_body, headers=_auth_header(raw_key)
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == create_body["name"]
    assert created["raw_key"].startswith("asahio_")
    assert created["last_four"]

    rotate_resp = await client.post(
        f"/keys/{existing_id}/rotate", headers=_auth_header(raw_key)
    )
    assert rotate_resp.status_code == 200
    rotated = rotate_resp.json()
    assert rotated["id"]
    assert rotated["raw_key"].startswith("asahio_")

    rotated_raw_key = rotated["raw_key"]
    created_id = created["id"]
    delete_resp = await client.delete(
        f"/keys/{created_id}", headers=_auth_header(rotated_raw_key)
    )
    assert delete_resp.status_code == 204
