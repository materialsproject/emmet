import pytest
import pytest_asyncio

from emmet.core.testing_utils import _get_test_files_dir
from tests.async_mongomock import AsyncMongomockClient


@pytest.fixture(scope="session")
def test_dir():
    return _get_test_files_dir("emmet.api")


@pytest_asyncio.fixture
async def mock_mongo_client():
    """Provide a mock MongoDB client for testing"""
    client = AsyncMongomockClient()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def mock_database(mock_mongo_client):
    """Provide a mock database"""
    return mock_mongo_client["test_db"]


@pytest_asyncio.fixture
async def mock_collection(mock_database):
    """Provide a mock collection with cleanup"""
    collection = mock_database["test_collection"]
    yield collection
    # Cleanup after test
    await collection.drop()


@pytest_asyncio.fixture
def mock_get_database(mock_mongo_client, monkeypatch):
    """Mock the database connection in your app"""

    async def _get_mock_database():
        return mock_mongo_client["test_db"]

    # Replace your actual get_database function
    monkeypatch.setattr("app.database.get_database", _get_mock_database)
    return _get_mock_database
