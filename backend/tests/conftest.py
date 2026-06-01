"""
Shared pytest fixtures for the CloudGuard test suite.

Architecture
============
- A separate `cloudguard_test` database is used so tests never touch real data.
- Tables are created once per session and TRUNCATED after every test, so each
  test starts with a clean slate.
- FastAPI's `get_db` and `get_aws_service` dependencies are overridden so
  routes use the test DB and a mock AWS service — no real AWS calls ever happen.
- httpx.AsyncClient drives the endpoints end-to-end in-process (no network).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text

# ── Important: import `app` (FastAPI instance) BEFORE anything that might
# shadow the name — `import app.models` binds `app` to the package, not the
# FastAPI instance, so we use `from app import models` instead.
from app.main import app as fastapi_app
from app.db.session import get_db
from app.api.deps import get_aws_service, get_current_user
from app.db.base import Base
from app.models.user import User
from app.services.aws_cost_service import AwsCostService
from app import models as _register_models  # noqa: F401 — registers all tables with Base.metadata

# Every cost/alert/recommendation/admin route now sits behind get_current_user.
# The vast majority of existing tests don't care *who* is logged in — they just
# need to be past the auth gate — so we override the dependency with a fixed
# fake user. Tests that exercise auth itself use `unauth_client`, which leaves
# the real get_current_user in place.
_FAKE_USER = User(id=1, email="tester@cloudguard.dev", hashed_password="x")

# ── Restrict anyio to asyncio only (default also tests trio, doubling runs) ──

@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


# ── Isolate SendGrid settings ─────────────────────────────────────────────────
# Real .env may contain a working SendGrid key + sender + recipient.  Without
# this fixture, sync tests would attempt actual network sends.  Individual
# tests that want to exercise the email path can opt in with their own
# monkeypatch (overrides our empty defaults for the duration of the test).

@pytest.fixture(autouse=True)
def _clear_sendgrid_settings(monkeypatch):
    monkeypatch.setattr("app.config.settings.sendgrid_api_key", "")
    monkeypatch.setattr("app.config.settings.alert_sender_email", "")
    monkeypatch.setattr("app.config.settings.alert_recipient_email", "")


# ── Encryption key for crypto_service ─────────────────────────────────────────
# The Settings/credentials tests encrypt and decrypt with Fernet. We pin a fixed
# valid test key (NOT the production one) and clear the cipher's lru_cache before
# and after each test so the key always takes effect and never leaks between runs.

_TEST_ENCRYPTION_KEY = "sUajX9OvLLfJYBPgXxw6gxAT2drCVRGD5pPszjyW5PI="


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch):
    from app.services import crypto_service

    monkeypatch.setattr("app.config.settings.encryption_key", _TEST_ENCRYPTION_KEY)
    crypto_service._get_fernet.cache_clear()
    yield
    crypto_service._get_fernet.cache_clear()


# ── Test database ─────────────────────────────────────────────────────────────

TEST_DB_URL = (
    "postgresql+asyncpg://cloudguard:cloudguard_dev@localhost:5433/cloudguard_test"
)

# NullPool: no cross-event-loop connection reuse. setup_test_database uses
# asyncio.run() (its own loop) while tests run in anyio's loop — a regular
# pool would return stale connections from the closed loop, breaking asyncpg.
test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


# ── Session-scoped: create tables once, drop when done ───────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Runs ONCE before the first test and ONCE after the last test.

    We use asyncio.run() here (not an async fixture) because session-scoped
    async fixtures have tricky interactions with anyio. Using a plain sync
    fixture with asyncio.run() avoids all those edge cases.
    """
    async def _create():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _drop():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await test_engine.dispose()

    asyncio.run(_create())
    yield
    asyncio.run(_drop())


# ── Function-scoped: wipe rows after every test ───────────────────────────────

@pytest.fixture(autouse=True)
def reset_tables():
    """
    Truncates all test-DB tables after every test so state never bleeds over.

    Why a local engine inside asyncio.run()?
      asyncio.run() creates its own event loop. asyncpg requires that every
      connection is created in the loop that uses it. A local NullPool engine
      creates one fresh connection inside that loop — clean, no cross-loop sharing.
    """
    yield  # test runs here

    async def _truncate():
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE TABLE aws_credentials, users, recommendations,"
                    " cost_records, aws_accounts RESTART IDENTITY CASCADE"
                )
            )
        await engine.dispose()

    asyncio.run(_truncate())


# ── DB session (shared between fixtures and route handlers in one test) ────────

@pytest.fixture
async def db_session() -> AsyncSession:
    """
    Async SQLAlchemy session pointing at cloudguard_test.

    The same instance is injected into both test fixtures that seed data AND
    route handlers (via the get_db override in `client` / `sync_client`).
    Routes therefore see seeded data without needing an extra commit.
    """
    async with TestSessionLocal() as session:
        yield session


# ── httpx client wired to the test database ───────────────────────────────────

@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """
    AsyncClient that calls FastAPI endpoints in-process.

    get_db is overridden so every route uses the test session.
    get_aws_service is also overridden with a mock that raises if called —
    these tests seed the DB so the AWS fallback should never be triggered.
    The override also removes the need for real credentials in .env.
    """
    async def _override_db():
        yield db_session

    # Raise loudly if any test accidentally hits the AWS fallback path.
    _no_aws = MagicMock(spec=AwsCostService)
    _no_aws.get_daily_costs = AsyncMock(
        side_effect=AssertionError("DB path should have been taken — AWS called unexpectedly")
    )
    _no_aws.get_cost_by_service = AsyncMock(
        side_effect=AssertionError("DB path should have been taken — AWS called unexpectedly")
    )

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_aws_service] = lambda: _no_aws
    # Sail past the auth gate as a fixed fake user — these tests aren't about login.
    fastapi_app.dependency_overrides[get_current_user] = lambda: _FAKE_USER

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac

    fastapi_app.dependency_overrides.pop(get_db, None)
    fastapi_app.dependency_overrides.pop(get_aws_service, None)
    fastapi_app.dependency_overrides.pop(get_current_user, None)


# ── Client WITHOUT the auth override — for testing auth itself ────────────────

@pytest.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncClient:
    """
    Like `client` but leaves the real get_current_user in place, so protected
    endpoints genuinely require a valid Bearer token.

    Used by the auth tests to prove registration/login work end-to-end and that
    protected routes reject anonymous requests. get_db still points at the test
    DB (so registered users persist for the login + token checks), and the AWS
    service is stubbed to fail loudly if a fallback path is ever hit.
    """
    async def _override_db():
        yield db_session

    _no_aws = MagicMock(spec=AwsCostService)
    _no_aws.get_daily_costs = AsyncMock(
        side_effect=AssertionError("AWS should not be called in auth tests")
    )

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_aws_service] = lambda: _no_aws

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac

    fastapi_app.dependency_overrides.pop(get_db, None)
    fastapi_app.dependency_overrides.pop(get_aws_service, None)


# ── Mock AWS service + patched STS ────────────────────────────────────────────

# Predetermined rows the mock AWS service returns — used by sync tests.
MOCK_COST_ROWS = [
    {"date": "2026-05-10", "service": "Amazon EC2", "cost": 18.50},
    {"date": "2026-05-10", "service": "Amazon S3",  "cost": 4.25},
    {"date": "2026-05-11", "service": "Amazon EC2", "cost": 20.00},
]


@pytest.fixture
def mock_aws_service() -> AwsCostService:
    """
    Fake AwsCostService that returns MOCK_COST_ROWS without hitting AWS.
    MagicMock(spec=AwsCostService) ensures unexpected calls fail loudly.
    """
    svc = MagicMock(spec=AwsCostService)
    svc.get_daily_costs = AsyncMock(return_value=MOCK_COST_ROWS)
    return svc


@pytest.fixture
async def sync_client(
    db_session: AsyncSession,
    mock_aws_service: AwsCostService,
) -> AsyncClient:
    """
    Client for admin sync tests.

    Overrides:
      1. get_db            → test DB session
      2. get_current_user  → fixed fake user (past the auth gate)

    The admin /sync route builds its AwsCostService from the logged-in user's
    saved credentials, so we patch `build_cost_service_for_user` to hand back
    the mock that returns MOCK_COST_ROWS — no real credential row or AWS needed.

    _fetch_account_id_sync is also patched directly because asyncio.to_thread()
    runs it in a worker thread where moto's thread-local mock context is not
    available — a plain patch is simpler and more reliable.
    """
    async def _override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: _FAKE_USER

    with patch(
        "app.api.v1.admin.build_cost_service_for_user",
        AsyncMock(return_value=mock_aws_service),
    ), patch(
        "app.jobs.cost_sync._fetch_account_id_sync",
        return_value="123456789012",
    ):
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as ac:
            yield ac

    fastapi_app.dependency_overrides.pop(get_db, None)
    fastapi_app.dependency_overrides.pop(get_current_user, None)


# ── Legacy fixture — kept for the unit tests in test_aws_cost.py ──────────────

@pytest.fixture
def aws_service() -> AwsCostService:
    """Returns an AwsCostService with a fake boto3 client (no real AWS calls)."""
    with patch("app.services.aws_cost_service.boto3.client"):
        service = AwsCostService(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )

    service._client = MagicMock()
    return service
