"""tests/test_export_evidence_cli.py — U7 / U8 / U10 (รีวิว tools 14 ต.ค. 2026)"""
from __future__ import annotations

import io
from datetime import datetime

import pytest

from tools import export_evidence

SAMPLE_CONN = [{"ts": "2026-08-01 10:00:00", "mac": "AA:BB:CC:DD:EE:01", "src_ip": "10.0.0.5",
                "dst_ip": "1.1.1.1", "dst_port": 443, "proto": "tcp"}]
SAMPLE_DNS = [{"ts": "2026-08-01 10:00:01", "client_ip": "10.0.0.5", "qname": "example.com"}]


class _FakeStdin:
    def __init__(self, text="", tty=False):
        self._text, self._tty = text, tty

    def isatty(self):
        return self._tty

    def readline(self):
        return self._text


# ---- U7
def test_natid_stdin_reads_line_and_no_warning():
    err = io.StringIO()
    got = export_evidence.resolve_natid(None, True, stdin=_FakeStdin("1234567890123\n"), err=err)
    assert got == "1234567890123" and err.getvalue() == ""


def test_natid_dash_on_tty_uses_getpass():
    got = export_evidence.resolve_natid("-", False, stdin=_FakeStdin(tty=True),
                                        getpass_fn=lambda prompt: " 1234567890123 ", err=io.StringIO())
    assert got == "1234567890123"


def test_natid_literal_value_still_works_but_warns_in_thai():
    err = io.StringIO()
    assert export_evidence.resolve_natid("1234567890123", False, err=err) == "1234567890123"
    assert "คำเตือน" in err.getvalue() and "history" in err.getvalue()


def test_no_natid_returns_none_and_empty_input_rejected():
    assert export_evidence.resolve_natid(None, False) is None
    with pytest.raises(ValueError):
        export_evidence.resolve_natid(None, True, stdin=_FakeStdin("\n"), err=io.StringIO())


def test_parser_accepts_bare_natid_and_stdin_flag():
    p = export_evidence.build_parser()
    a = p.parse_args(["--natid", "--from", "2026-08-01", "--to", "2026-08-02"])
    assert a.natid == "-"
    a = p.parse_args(["--natid-stdin", "--from", "2026-08-01", "--to", "2026-08-02"])
    assert a.natid_stdin and a.natid is None
    with pytest.raises(SystemExit):  # ใช้คู่ --mac ไม่ได้
        p.parse_args(["--natid-stdin", "--mac", "AA:BB:CC:DD:EE:01", "--from", "a", "--to", "b"])


# ---- U8
def test_export_audits_actor_and_result_without_natid(tmp_path, monkeypatch):
    from common import audit
    calls = []
    monkeypatch.setattr(audit, "log_required", lambda a, **kw: calls.append(("req", a, kw)))
    monkeypatch.setattr(audit, "log", lambda a, **kw: calls.append(("log", a, kw)))
    result = export_evidence.export(
        None, datetime(2026, 8, 1), datetime(2026, 8, 2), tmp_path, lambda *a: SAMPLE_CONN,
        lambda *a: SAMPLE_DNS, customer={"id": 7, "natid_masked": "1-2345-XXXXX-XX-3"},
        actor="pi-tech", audit_result=True)
    assert [c[0] for c in calls] == ["req", "log"]
    assert "actor=pi-tech" in calls[0][2]["detail"]
    detail = calls[1][2]["detail"]
    assert "actor=pi-tech" in detail and str(tmp_path) in detail
    assert f"conn_rows={result['conn_file'].row_count}" in detail
    assert result["conn_file"].sha256 in detail and result["dns_file"].sha256 in detail
    assert calls[1][2]["target"] == "customer:7"


def test_default_export_still_has_single_audit_row(tmp_path, monkeypatch):
    """เว็บ admin เรียก export() แบบเดิม -- ต้องไม่ได้แถว audit เพิ่ม"""
    from common import audit
    calls = []
    monkeypatch.setattr(audit, "log_required", lambda a, **kw: calls.append(a))
    monkeypatch.setattr(audit, "log", lambda a, **kw: calls.append(a))
    export_evidence.export(None, datetime(2026, 8, 1), datetime(2026, 8, 2), tmp_path,
                           lambda *a: [], lambda *a: [])
    assert len(calls) == 1


def test_cli_actor_prefers_sudo_user(monkeypatch):
    monkeypatch.setenv("SUDO_USER", "alice")
    assert export_evidence.cli_actor() == "alice"


# ---- U10
def test_write_private_never_overwrites(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("evidence", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_evidence._write_private(p, "new")
    assert p.read_text(encoding="utf-8") == "evidence"


def test_same_second_export_gets_suffix_not_overwrite(tmp_path, monkeypatch):
    from common import audit
    monkeypatch.setattr(audit, "log_required", lambda *a, **kw: None)

    class _FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 3, 12, 0, 0)

    monkeypatch.setattr(export_evidence, "datetime", _FixedDT)
    kw = dict(mac=None, start=datetime(2026, 8, 1), end=datetime(2026, 8, 2), out_dir=tmp_path,
              query_conn_fn=lambda *a: SAMPLE_CONN, query_dns_fn=lambda *a: SAMPLE_DNS)
    r1 = export_evidence.export(**kw)
    first = r1["conn_file"].path.read_bytes()
    r2 = export_evidence.export(**kw)
    r3 = export_evidence.export(**kw)
    assert len({r1["conn_file"].path, r2["conn_file"].path, r3["conn_file"].path}) == 3
    assert r2["conn_file"].path.name.endswith("-2.csv")
    assert r3["manifest_path"].name.endswith("-3.json")
    assert r1["conn_file"].path.read_bytes() == first
