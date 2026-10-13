"""common/db.py ต้องตั้ง timeout ทุกการเชื่อมต่อ -- DB ค้างแล้ว request/collector ห้ามแขวนตลอดไป"""
from common import db


def test_cfg_has_timeouts(monkeypatch):
    for k in ("DB_CONNECT_TIMEOUT", "DB_READ_TIMEOUT", "DB_WRITE_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    cfg = db._cfg()
    assert (cfg["connect_timeout"], cfg["read_timeout"], cfg["write_timeout"]) == (5, 600, 60)


def test_timeouts_configurable_by_env_and_bad_values_fall_back(monkeypatch):
    monkeypatch.setenv("DB_READ_TIMEOUT", "300")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "abc")
    cfg = db._cfg()
    assert cfg["read_timeout"] == 300 and cfg["connect_timeout"] == 5


def test_get_conn_passes_timeouts_and_allows_override(monkeypatch):
    seen = {}

    class Conn:
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(db.pymysql, "connect", lambda **kw: seen.update(kw) or Conn())
    with db.get_conn(read_timeout=1200):
        pass
    assert seen["read_timeout"] == 1200 and seen["connect_timeout"] == 5 and seen["write_timeout"] == 60
