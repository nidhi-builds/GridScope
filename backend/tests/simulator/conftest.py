import pytest
from sqlalchemy.orm import Session

from app.db import engine


@pytest.fixture
def session():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as scoped:
                yield scoped
        finally:
            transaction.rollback()
