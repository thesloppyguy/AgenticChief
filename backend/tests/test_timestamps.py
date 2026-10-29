from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import Column, Integer, create_engine, select
from sqlalchemy.orm import Session, declarative_base

from app.core.security import Role, make_token
from app.db.types import UtcDateTime
from tests.api.conftest import client  # noqa: F401


def test_naive_and_foreign_zone_values_are_stored_as_utc_and_come_back_aware():
    Base = declarative_base()

    class T(Base):
        __tablename__ = "t"
        id = Column(Integer, primary_key=True)
        at = Column(UtcDateTime())

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    ist = timezone(timedelta(hours=5, minutes=30))
    with Session(eng) as s:
        s.add_all([T(at=datetime(2026, 10, 29, 12, 0, tzinfo=ist)), T(at=datetime(2026, 10, 29, 6, 30)), T(at=None)])
        s.commit()
        rows = [r.at for r in s.scalars(select(T).order_by(T.id))]
    assert rows[0] == rows[1] == datetime(2026, 10, 29, 6, 30, tzinfo=UTC)   # 12:00 IST is 06:30 UTC; naive means UTC
    assert rows[0].tzinfo is UTC and rows[2] is None


def test_api_timestamps_carry_an_explicit_zone_so_browsers_do_not_read_them_as_local_time(client):
    editor = {"Authorization": f"Bearer {make_token('erin', Role.EDITOR, None)}"}
    client.post("/inputs", json={"company_id": 1, "period": "2026-10", "kpi_key": "gptw_score", "value": 70}, headers=editor)
    at = client.get("/inputs/history", params={"company_id": 1}, headers=editor).json()[0]["at"]
    assert at.endswith(("Z", "+00:00")), at
    parsed = datetime.fromisoformat(at)
    assert abs(datetime.now(UTC) - parsed) < timedelta(seconds=30)             # and it really is "now", not shifted
