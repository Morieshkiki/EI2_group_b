import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient
from app.main import app
from app.config import MONGO_ADDRESS, MONGO_DB_NAME


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    client = AsyncIOMotorClient(MONGO_ADDRESS)
    db = client[MONGO_DB_NAME]

    # Clean up before each test
    await db["buildings"].delete_many({})
    await db["sensors"].delete_many({})
    await db["sensor_readings"].delete_many({})

    yield

    # Clean up after each test
    await db["buildings"].delete_many({})
    await db["sensors"].delete_many({})
    await db["sensor_readings"].delete_many({})
