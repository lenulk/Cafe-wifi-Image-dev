"""tests/test_reset_admin.py — U6: reset_admin ลง audit ใน transaction เดียวกับการเปลี่ยนรหัสผ่าน"""
from __future__ import annotations

import contextlib

import pytest

from tools import reset_admin


class _Cur:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, args=()):
        self.log.append((sql, args))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _Cur(self.log)


def _setup(monkeypatch, log, fail_audit=False):
    monkeypatch.setattr(reset_admin, "query_one", lambda *a, **kw: {"id": 3, "role": "admin"})
    monkeypatch.setattr(reset_admin.crypto, "check_admin_password", lambda p: [])
    monkeypatch.setattr(reset_admin.crypto, "hash_password", lambda p: "HASH")
    monkeypatch.setattr(reset_admin.getpass, "getpass", lambda prompt="": "Str0ng-Passw0rd!x")

    @contextlib.contextmanager
    def fake_conn(**kw):
        conn = _Conn(log)
        try:
            yield conn
        except Exception:
            log.append(("ROLLBACK", ()))
            raise
        else:
            log.append(("COMMIT", ()))

    monkeypatch.setattr(reset_admin, "get_conn", fake_conn)
    if fail_audit:
        def boom(*a, **kw):
            raise RuntimeError("audit down")
        monkeypatch.setattr(reset_admin.audit, "log_required", boom)
    monkeypatch.setattr("sys.argv", ["reset_admin", "somchai"])


def test_reset_writes_audit_in_same_transaction_with_actor(monkeypatch):
    log = []
    _setup(monkeypatch, log)
    monkeypatch.setenv("SUDO_USER", "pi-tech")
    assert reset_admin.main() == 0
    sqls = [x[0] for x in log]
    assert sqls[0].startswith("UPDATE staff") and sqls[1].startswith("INSERT INTO audit_log")
    assert sqls[-1] == "COMMIT"
    audit_args = log[1][1]
    assert audit_args[1] == "staff_reset_password" and audit_args[2] == "somchai"
    assert "pi-tech" in audit_args[4] and "CLI" in audit_args[4]
    assert "Str0ng" not in str(log)  # ไม่มีรหัสผ่านใน audit


def test_reset_fails_closed_when_audit_fails(monkeypatch, capsys):
    log = []
    _setup(monkeypatch, log, fail_audit=True)
    assert reset_admin.main() == 1
    assert ("ROLLBACK", ()) in log and ("COMMIT", ()) not in log
    assert "audit down" in capsys.readouterr().err


def test_cli_actor_prefers_sudo_user(monkeypatch):
    monkeypatch.setenv("SUDO_USER", "alice")
    assert reset_admin.cli_actor() == "alice"
    monkeypatch.delenv("SUDO_USER")
    monkeypatch.setattr(reset_admin.os, "getlogin", lambda: "bob")
    assert reset_admin.cli_actor() == "bob"
    monkeypatch.setattr(reset_admin.os, "getlogin", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setenv("USER", "carol")
    assert reset_admin.cli_actor() == "carol"
