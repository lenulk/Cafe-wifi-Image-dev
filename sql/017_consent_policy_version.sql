-- ============================================================================
--  017_consent_policy_version.sql — บันทึกเวอร์ชันนโยบายความเป็นส่วนตัวที่ลูกค้ายินยอม
--  MariaDB 10.6+ / 11.x
-- ============================================================================
-- access_request.consent_at บอกแค่ "เมื่อไหร่" ไม่บอกว่ายินยอมนโยบายฉบับไหน (PDPA ต้องพิสูจน์ได้)
-- ค่ามาจาก common/policy.py::PRIVACY_POLICY_VERSION · แถวเก่า = NULL (ก่อนมีการบันทึกเวอร์ชัน)
-- รันซ้ำได้: ADD COLUMN IF NOT EXISTS
ALTER TABLE access_request ADD COLUMN IF NOT EXISTS consent_version VARCHAR(32) NULL AFTER consent_at;
