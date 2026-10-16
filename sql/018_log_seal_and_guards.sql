-- 018: ผนึกแถว log ในฐานข้อมูลรายวัน (hash chain) + trigger กันแก้/ลบหลักฐาน (A8/H2, 16 ต.ค. 2026)
--
-- ปัญหาเดิม (ยืนยันบน Pi): user ฐานข้อมูลตัวเดียวของทุก service มี UPDATE/DELETE ทุกตาราง และ hash chain
-- ของ logger.integrity ผนึกแค่ "ไฟล์" log ที่หมุนแล้ว ไม่ครอบแถว conn_log/dns_log/audit_log ในฐานข้อมูลเลย
-- -> ใครได้รหัสฐานข้อมูลลบ/แก้หลักฐานได้โดยไม่มีอะไรจับ
--
-- ชั้นที่ 1 (ไฟล์นี้): log_seal = ผลรวม SHA-256 ของแถวแต่ละวันต่อกันเป็นสาย (logger/db_seal.py เขียน/ตรวจ)
-- ชั้นที่ 2 (ไฟล์นี้): trigger -- เว็บแอปที่ถูกเจาะต้องแก้หลักฐานที่ยังอยู่ในระยะเก็บไม่ได้แม้มีสิทธิ์ UPDATE
-- ชั้นที่ 3 (install.sh setup_db_users): user แยกต่อ service ไม่มีใครนอกจากงานบำรุงรักษา (root) ลบ log ได้
-- user ของแอปไม่มีสิทธิ์ TRIGGER/DROP จึงถอด trigger เหล่านี้เองไม่ได้

CREATE TABLE IF NOT EXISTS log_seal (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  table_name   VARCHAR(32)  NOT NULL,
  seal_date    DATE         NOT NULL,
  row_count    BIGINT       NOT NULL,
  min_id       BIGINT       NULL,
  max_id       BIGINT       NULL,
  columns      VARCHAR(512) NOT NULL,   -- ลำดับคอลัมน์ที่ใช้คิด hash (ตรวจย้อนหลังได้แม้ภายหลังมี ALTER ADD COLUMN)
  rows_sha256  CHAR(64)     NOT NULL,
  prev_chain   CHAR(64)     NULL,
  chain_sha256 CHAR(64)     NOT NULL,
  sealed_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_table_date (table_name, seal_date)
) ENGINE=InnoDB;

DELIMITER $$

-- log_seal เพิ่มได้อย่างเดียว
DROP TRIGGER IF EXISTS log_seal_no_update $$
CREATE TRIGGER log_seal_no_update BEFORE UPDATE ON log_seal FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'log_seal is append-only' $$
DROP TRIGGER IF EXISTS log_seal_no_delete $$
CREATE TRIGGER log_seal_no_delete BEFORE DELETE ON log_seal FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'log_seal is append-only' $$

-- ข้อมูลจราจร: ไม่มีโค้ดไหน UPDATE เลย (ลบตามอายุด้วย purge_old_data ซึ่งคุมด้วยสิทธิ์ DELETE ของ user แทน
-- -- trigger ลบรายแถวจะทำให้ purge หลายล้านแถวช้าลงมาก)
DROP TRIGGER IF EXISTS conn_log_no_update $$
CREATE TRIGGER conn_log_no_update BEFORE UPDATE ON conn_log FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'conn_log is evidence: UPDATE not allowed' $$
DROP TRIGGER IF EXISTS dns_log_no_update $$
CREATE TRIGGER dns_log_no_update BEFORE UPDATE ON dns_log FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'dns_log is evidence: UPDATE not allowed' $$

-- audit_log: ไม่มีโค้ดไหนลบแถว (T8: ไม่ลบอัตโนมัติ) · UPDATE มีแค่ปุ่มล้างข้อมูลลูกค้า (/audit/scrub) ซึ่งรับ
-- cutoff >= 180 วัน และแก้ได้แค่ target/detail -- บังคับเงื่อนไขเดียวกันที่ฐานข้อมูล
DROP TRIGGER IF EXISTS audit_log_no_delete $$
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is evidence: DELETE not allowed' $$
DROP TRIGGER IF EXISTS audit_log_scrub_only $$
CREATE TRIGGER audit_log_scrub_only BEFORE UPDATE ON audit_log FOR EACH ROW
BEGIN
  IF OLD.ts >= NOW() - INTERVAL 180 DAY
     OR NEW.id <> OLD.id OR NEW.ts <> OLD.ts OR NEW.action <> OLD.action
     OR NOT (NEW.staff_id <=> OLD.staff_id) OR NOT (NEW.client_ip <=> OLD.client_ip) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'audit_log: only target/detail of rows older than 180 days may change (scrub)';
  END IF;
END $$

DELIMITER ;
