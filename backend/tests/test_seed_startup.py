from pathlib import Path

from app import seed as seed_module


def test_packaged_startup_finds_repository_migration_config(monkeypatch):
    # Break caught: the installed app looks beside site-packages and cannot start migrations.
    monkeypatch.setattr(seed_module, "__file__", "/usr/local/lib/python3.12/site-packages/app/seed.py")
    monkeypatch.chdir("/app")

    assert seed_module._alembic_config_path() == Path("/app/backend/alembic.ini")
