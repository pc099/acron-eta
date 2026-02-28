import uuid

from httpx import AsyncClient


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_keys_crud_lifecycle(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    # List keys with API key auth
    list_resp = await client.get("/keys", headers=_auth_header(raw_key))
    assert list_resp.status_code == 200
    keys = list_resp.json()
    assert isinstance(keys, list)
    assert keys
    existing_id = keys[0]["id"]
    assert "raw_key" not in keys[0]
    assert "key_hash" not in keys[0]

    # Create a new key
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
    assert created["raw_key"].startswith("asahi_")
    assert created["last_four"]

    # Rotate the existing key (revokes old key, creates new one)
    rotate_resp = await client.post(
        f"/keys/{existing_id}/rotate", headers=_auth_header(raw_key)
    )
    assert rotate_resp.status_code == 200
    rotated = rotate_resp.json()
    assert rotated["id"]
    assert rotated["raw_key"].startswith("asahi_")

    # Use the newly created key from the create step for further auth
    # (the original raw_key was revoked by the rotation above)
    new_raw_key = created["raw_key"]

    # Revoke the rotated key using the new key for auth
    rotated_id = rotated["id"]
    delete_resp = await client.delete(
        f"/keys/{rotated_id}", headers=_auth_header(new_raw_key)
    )
    assert delete_resp.status_code == 204

