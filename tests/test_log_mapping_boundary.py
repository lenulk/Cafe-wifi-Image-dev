"""SESSION_MATCH: session A จบที่ T, B (MAC+IP เดิม) เริ่มที่ T -- แถวเวลา T ต้องเป็นของ B เท่านั้น"""
import sqlite3

from common import log_mapping


def test_session_match_upper_bound_is_exclusive():
    sql = log_mapping.session_match("cl", "src_ip", log_mapping.CONN_TSEXPR)
    assert "COALESCE(cl.started_at, cl.ts) < s.ended_at" in sql
    assert "<= s.ended_at" not in sql


def test_boundary_row_maps_to_new_session_only():
    # รัน SESSION_MATCH จริงบน sqlite (COALESCE/CASE/COUNT/MAX ใช้ได้เหมือนกัน)
    db = sqlite3.connect(":memory:")
    db.executescript("""
      CREATE TABLE portal_session (id INT, mac TEXT, ip TEXT, authenticated_at INT, ended_at INT);
      INSERT INTO portal_session VALUES (1,'m','1.1.1.1',100,200),(2,'m','1.1.1.1',200,NULL);
      CREATE TABLE cl (mac TEXT, src_ip TEXT, started_at INT, ts INT);
      INSERT INTO cl VALUES ('m','1.1.1.1',NULL,200),('m','1.1.1.1',NULL,199),('m','1.1.1.1',NULL,201);
    """)
    sql = log_mapping.session_match("cl", "src_ip", log_mapping.CONN_TSEXPR)
    got = [r[0] for r in db.execute(f"SELECT ({sql}) FROM cl ORDER BY ts")]
    assert got == [1, 2, 2]
