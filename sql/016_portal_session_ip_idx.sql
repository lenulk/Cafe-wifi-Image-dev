-- ============================================================================
--  016_portal_session_ip_idx.sql — ดัชนี (ip, authenticated_at) ของ portal_session
--  MariaDB 10.6+ / 11.x
-- ============================================================================
-- cafe-logger หา MAC จาก IP ตอน conntrack ไม่มี MAC (SELECT DISTINCT mac ... WHERE ip=%s AND
-- authenticated_at ...) และ subquery โยง log -> ลูกค้า (mac+ip+เวลา) ค้นด้วย ip -- มีแต่
-- idx_mac_time (mac, started_at) ตารางใหญ่แล้วต้องสแกนเต็ม
-- รันซ้ำได้: IF NOT EXISTS
CREATE INDEX IF NOT EXISTS idx_ip_auth ON portal_session (ip, authenticated_at);
