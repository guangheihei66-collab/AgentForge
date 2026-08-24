from app.storage.database import database_url, engine


def test_tests_force_an_isolated_in_memory_database():
    assert database_url() == "sqlite+pysqlite:///:memory:"
    assert engine.url.database == ":memory:"
