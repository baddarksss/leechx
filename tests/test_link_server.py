import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.db import repo
from app.services.filestore import FileStore
from app.services.link_server import LinkServer
from app.services.linktoken import make_token
from app.services.runtime_settings import RuntimeSettings

CONTENT = b"0123456789" * 100


@pytest.fixture()
def setup(db):
    store = FileStore(db.files_dir, db.tmp_dir)
    server = LinkServer(db, RuntimeSettings(db), store)
    return db, store, server


@pytest.mark.asyncio
async def test_health_and_serving(setup):
    cfg, store, server = setup
    path = store.link_path("abc", "movie.mp4")
    path.write_bytes(CONTENT)
    await repo.create_shared("abc", 1, str(path), "movie.mp4", "video/mp4", len(CONTENT), 3600)
    token = make_token("abc", cfg.link_secret, 3600)

    async with TestClient(TestServer(server.build_app())) as client:
        health = await client.get("/health")
        assert health.status == 200
        data = await health.json()
        assert data["status"] == "ok"
        assert data["shared_files"] == 1

        resp = await client.get(f"/f/{token}")
        assert resp.status == 200
        assert await resp.read() == CONTENT
        assert resp.headers["Accept-Ranges"] == "bytes"
        assert "movie.mp4" in resp.headers["Content-Disposition"]

        rng = await client.get(f"/f/{token}", headers={"Range": "bytes=0-3"})
        assert rng.status == 206
        assert await rng.read() == b"0123"
        assert rng.headers["Content-Range"] == f"bytes 0-3/{len(CONTENT)}"

        suffix = await client.get(f"/f/{token}", headers={"Range": "bytes=-4"})
        assert suffix.status == 206
        assert await suffix.read() == CONTENT[-4:]

        head = await client.head(f"/f/{token}")
        assert head.status == 200
        assert head.headers["Content-Length"] == str(len(CONTENT))

    traffic = await repo.traffic_totals()
    assert traffic["direct_link_serve_bytes"] == len(CONTENT) + 4 + 4
    assert traffic["uploaded_bytes"] == len(CONTENT) + 8
    assert traffic["downloaded_bytes"] == 0


@pytest.mark.asyncio
async def test_bad_tokens(setup):
    cfg, store, server = setup
    path = store.link_path("abc", "a.mp4")
    path.write_bytes(CONTENT)
    await repo.create_shared("abc", 1, str(path), "a.mp4", "video/mp4", len(CONTENT), 3600)

    async with TestClient(TestServer(server.build_app())) as client:
        tampered = make_token("abc", "wrong-secret", 3600)
        assert (await client.get(f"/f/{tampered}")).status == 410

        expired = make_token("abc", cfg.link_secret, -5)
        assert (await client.get(f"/f/{expired}")).status == 410

        missing = make_token("nope", cfg.link_secret, 3600)
        assert (await client.get(f"/f/{missing}")).status == 404


@pytest.mark.asyncio
async def test_path_traversal_blocked(setup):
    cfg, store, server = setup
    outside = cfg.data_dir / "secret.txt"
    outside.write_text("top secret")
    await repo.create_shared("evil", 1, str(outside), "secret.txt", "text/plain", 9, 3600)
    token = make_token("evil", cfg.link_secret, 3600)

    async with TestClient(TestServer(server.build_app())) as client:
        resp = await client.get(f"/f/{token}")
        assert resp.status == 403
