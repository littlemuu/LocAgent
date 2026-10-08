"""Explicit additive schema initialization: python -m locagent_service.db."""
from locagent_service.config import Settings
from locagent_service.store import TaskStore


def main():
    try:
        TaskStore(Settings.from_env()).initialize()
    except Exception:
        raise SystemExit('Database initialization failed; check local PostgreSQL and settings') from None
    print('PostgreSQL schema version 2 ready')


if __name__ == '__main__':
    main()
