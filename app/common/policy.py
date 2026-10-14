"""
common/policy.py — เวอร์ชันนโยบายความเป็นส่วนตัวที่ลูกค้ายอมรับ

แก้เนื้อหา fas/templates/policy.html (และ docs/privacy-policy-th.md) เมื่อไหร่ ให้ขยับค่านี้เป็นวันที่แก้
คำขอใหม่จะบันทึกเวอร์ชันนี้ลง access_request.consent_version (sql/017) -- ใช้พิสูจน์ได้ว่าลูกค้าแต่ละคน
ยินยอมตามนโยบายฉบับไหน (PDPA) · คำขอเก่าก่อน 017 เป็น NULL = ฉบับก่อนมีการบันทึกเวอร์ชัน
"""
PRIVACY_POLICY_VERSION = "2026-10-14"
