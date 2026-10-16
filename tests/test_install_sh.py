"""ทดสอบฟังก์ชันใน install.sh โดย source เข้า bash (CAFEWIFI_SOURCE_ONLY=1) แล้วดักคำสั่งที่แตะระบบ"""
import shutil
import subprocess
from pathlib import Path

import pytest

BASH = shutil.which("bash")
if BASH is None:
    pytest.skip("ไม่พบ bash", allow_module_level=True)

REPO = Path(__file__).resolve().parent.parent

# write_file ถูกแทนด้วยตัวเก็บ stdin ลง $OUT · run/run_sh/svc แค่บันทึกคำสั่ง
PRELUDE = r'''
set -uo pipefail
CAFEWIFI_SOURCE_ONLY=1 source "$REPO/install.sh"
set +e
write_file() { cat > "$OUT/${1//\//_}"; echo "${2:-0644} ${3:-}" > "$OUT/${1//\//_}.meta"; }
run()    { echo "run $*" >> "$OUT/cmds.log"; return 0; }
run_sh() { echo "run_sh $1" >> "$OUT/cmds.log"; return 0; }
svc()    { echo "svc $*" >> "$OUT/cmds.log"; return 0; }
'''


def call(tmp_path, body, pre=""):
    """รัน body ใน bash หลัง source install.sh · pre = bash เสริม (override) ก่อนเรียก"""
    script = PRELUDE + pre + "\n" + body
    r = subprocess.run(
        [BASH, "-c", script], capture_output=True, text=True, encoding="utf-8",
        env={**__import__("os").environ, "REPO": REPO.as_posix(), "OUT": tmp_path.as_posix()},
    )
    return r


def unit(tmp_path, name):
    return (tmp_path / f"_etc_systemd_system_{name}").read_text(encoding="utf-8")


@pytest.fixture
def services(tmp_path):
    r = call(tmp_path, "install_services", pre="INIT_SYS=systemd; DRY_RUN=0")
    assert r.returncode == 0, r.stderr
    return tmp_path


def test_maintenance_waits_for_db_and_time(services):
    u = unit(services, "cafe-maintenance.service")
    assert "Wants=mariadb.service time-sync.target" in u
    assert "After=mariadb.service time-sync.target" in u


def test_logger_always_restarts(services):
    u = unit(services, "cafe-logger.service")
    assert "Restart=always" in u and "Restart=on-failure" not in u


@pytest.mark.parametrize("name", ["cafe-enforce.timer", "cafe-bypass-detect.timer"])
def test_timers_have_accuracy_1s(services, name):
    assert "AccuracySec=1s" in unit(services, name)


def test_secure_tls_key_is_root_only(tmp_path):
    r = call(tmp_path, 'secure_tls_key /x/server.key',
             pre='chmod() { echo "chmod $*" >> "$OUT/cmds.log"; }; chown() { echo "chown $*" >> "$OUT/cmds.log"; }')
    assert r.returncode == 0, r.stderr
    log = (tmp_path / "cmds.log").read_text()
    assert "chmod 0600 /x/server.key" in log and "chown root:root /x/server.key" in log


def test_make_tls_cert_dies_visibly_when_openssl_fails(tmp_path):
    # run ถูกดักไว้ จึงไม่แตะ /etc จริง · ไม่มี server.crt ใน ETC_DIR/tls บนเครื่องเทสต์ -> เข้าสาขาสร้างใบ
    r = call(tmp_path, "make_tls_cert", pre='DRY_RUN=0; openssl() { echo "boom detail" >&2; return 1; }')
    assert r.returncode != 0
    assert "สร้างใบรับรองไม่สำเร็จ" in r.stdout + r.stderr
    assert "boom detail" in r.stdout + r.stderr


def test_build_opennds_dies_when_pinned_tag_clone_fails(tmp_path):
    pre = '''DRY_RUN=0; SKIP_OPENNDS=0; SKIP_NETWORK=0
command() { return 1; }
run_sh() { echo "run_sh $1" >> "$OUT/cmds.log"; [[ "$1" == "git clone"* ]] && return 1; return 0; }
'''
    r = call(tmp_path, "build_opennds", pre=pre)
    assert r.returncode != 0
    log = (tmp_path / "cmds.log").read_text()
    assert log.count("git clone") == 1 and "--branch" in log
    assert "--opennds-ref" in r.stdout + r.stderr


def test_write_file_writes_content_intact(tmp_path):
    target = (tmp_path / "sub" / "f.conf").as_posix()
    # ใช้ write_file จริงของ install.sh (ไม่ override)
    script = (f'set -uo pipefail\nCAFEWIFI_SOURCE_ONLY=1 source "$REPO/install.sh"\nDRY_RUN=0\n'
              f'printf "a b\nfaskey=1\n" | write_file "{target}" 0600')
    r = subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8",
                       env={**__import__("os").environ, "REPO": REPO.as_posix()})
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "sub" / "f.conf").read_text() == "a b\nfaskey=1\n"


def validate(tmp_path, cidr="10.10.0.1/24", start="10.10.0.100", end="10.10.0.250", defaults=False):
    pre = "" if defaults else f'CLIENT_CIDR="{cidr}"; DHCP_START="{start}"; DHCP_END="{end}"'
    return call(tmp_path, "validate_net_args", pre=pre)


def test_net_defaults_pass(tmp_path):
    r = validate(tmp_path, defaults=True)
    assert r.returncode == 0, r.stderr


def test_net_other_valid_subnet_passes(tmp_path):
    assert validate(tmp_path, "192.168.7.1/24", "192.168.7.10", "192.168.7.20").returncode == 0


@pytest.mark.parametrize("cidr", ["10.10.0.1/16", "10.10.0.1", "10.10.0.256/24", "abc/24"])
def test_net_bad_cidr_rejected(tmp_path, cidr):
    assert validate(tmp_path, cidr).returncode != 0


def test_net_range_outside_subnet_rejected(tmp_path):
    assert validate(tmp_path, start="10.10.1.100", end="10.10.1.200").returncode != 0


def test_net_start_after_end_rejected(tmp_path):
    assert validate(tmp_path, start="10.10.0.200", end="10.10.0.100").returncode != 0


def test_net_range_covering_gateway_rejected(tmp_path):
    assert validate(tmp_path, start="10.10.0.1", end="10.10.0.50").returncode != 0
    assert validate(tmp_path, "10.10.0.150/24").returncode != 0  # gateway .150 อยู่ใน 100-250


def test_net_non_ip_range_rejected(tmp_path):
    assert validate(tmp_path, start="10.10.0.x", end="10.10.0.250").returncode != 0


# ------------------------------------------------------------------ รีวิว tools 14 ต.ค. (U12, T9)
def test_install_app_files_excludes_lab_and_bench_tools(tmp_path):
    """U12: lab_*/bench_* ไม่ลงเครื่องจริง (แม้มีของเก่าค้างอยู่จากรุ่นก่อน) · เครื่องมือจริงยังอยู่"""
    src, dst = tmp_path / "src", tmp_path / "opt"
    (src / "tools").mkdir(parents=True)
    for d in ("app", "sql", "docs"):
        (src / d).mkdir()
    (dst / "tools").mkdir(parents=True)
    for n in ("backup_db.py", "check_disk.py", "lab_client.sh", "lab_ra_sim.py", "lab_fulltest.sh", "bench_dns_search.py"):
        (src / "tools" / n).write_text("x")
    (dst / "tools" / "lab_old.sh").write_text("stale")
    # SCRIPT_DIR/OPT_DIR เป็น readonly หลัง source -- สลับ path ในคำสั่งก่อนรันจริงแทน
    pre = ('INIT_SYS=systemd; DRY_RUN=0\n'
           f'run_sh() {{ local c="${{1//$SCRIPT_DIR/{src.as_posix()}}}"; c="${{c//$OPT_DIR/{dst.as_posix()}}}"; '
           'case "$c" in cp*|rm*) bash -c "$c";; esac; }')
    r = call(tmp_path, "install_app_files", pre=pre)
    assert r.returncode == 0, r.stderr
    left = sorted(p.name for p in (dst / "tools").iterdir())
    assert left == ["backup_db.py", "check_disk.py"]


def test_install_app_files_strips_group_write_after_chown(tmp_path):
    """Pi 2026-10-16: ต้นฉบับจาก git archive เป็น 664 + cp -a + chown root:cafewifi = เว็บแอปแก้โค้ดที่ root รันได้"""
    r = call(tmp_path, "INIT_SYS=systemd; DRY_RUN=0; install_app_files")
    assert r.returncode == 0, r.stderr
    cmds = (tmp_path / "cmds.log").read_text(encoding="utf-8").splitlines()
    chown = next(i for i, c in enumerate(cmds) if "chown -R root:" in c)
    strip = [i for i, c in enumerate(cmds) if "-type f" in c and "chmod go-w" in c]
    assert strip and strip[0] > chown, "ต้องถอดสิทธิ์เขียนของกลุ่ม/คนอื่นหลัง chown"


def test_nothing_installed_references_lab_or_bench_tools():
    """ไฟล์ที่ติดตั้งลงเครื่อง (install.sh/image/app) ต้องไม่เรียก lab_*/bench_* -- กันตัดแล้วของพัง"""
    import re
    pat = re.compile(r"tools[/.](lab_|bench_)")
    for rel in ("install.sh", "image/firstboot", "image/check-image.sh", "app"):
        base = REPO / rel
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file() and p.suffix in
                                                  {".sh", ".py", ".service", ".timer", ".html", ""}]
        for f in files:
            text = f.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if pat.search(line) and "rm -f" not in line:
                    pytest.fail(f"{f}: {line.strip()}")


def test_check_disk_has_its_own_15min_timer(services):
    s = unit(services, "cafe-check-disk.service")
    assert "ExecStart=" in s and "-m tools.check_disk" in s
    assert "EnvironmentFile=" in s and "secrets.env" in s and "PYTHONPATH=" in s
    assert "Type=oneshot" in s
    t = unit(services, "cafe-check-disk.timer")
    assert "OnBootSec=5min" in t and "OnUnitActiveSec=15min" in t and "AccuracySec=1min" in t
    assert "WantedBy=timers.target" in t


def test_start_services_enables_check_disk_timer(tmp_path):
    r = call(tmp_path, "start_services", pre="INIT_SYS=systemd; DRY_RUN=0; SKIP_NETWORK=1")
    assert r.returncode == 0, r.stderr
    assert "cafe-check-disk.timer" in (tmp_path / "cmds.log").read_text(encoding="utf-8")


def test_maintenance_seals_db_logs_after_purge_and_before_backup(services):
    """A8/H2: ผนึกแถว log หลัง purge (ไม่ผนึกแถวที่กำลังจะถูกลบ) และก่อน backup (ไฟล์สำรองมี head ล่าสุด)"""
    lines = [l for l in unit(services, "cafe-maintenance.service").splitlines() if l.startswith("ExecStart=")]
    mods = [l.split(" -m ")[1] for l in lines if " -m " in l]
    assert mods.index("tools.purge_old_data") < mods.index("logger.db_seal") < mods.index("tools.backup_db")


def test_setup_database_applies_018_log_guards():
    src = (REPO / "install.sh").read_text(encoding="utf-8")
    assert "sql/018_log_seal_and_guards.sql" in src
    sql = (REPO / "sql" / "018_log_seal_and_guards.sql").read_text(encoding="utf-8")
    for trig in ("conn_log_no_update", "dns_log_no_update", "audit_log_no_delete", "audit_log_scrub_only",
                 "log_seal_no_update", "log_seal_no_delete"):
        assert f"DROP TRIGGER IF EXISTS {trig}" in sql, "รันซ้ำได้"


# ---------------------------------------------------------------- A8/H2 user ฐานข้อมูลแยกต่อ service
def _grants(tmp_path):
    r = call(tmp_path, "db_grants_sql")
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def test_no_web_or_logger_user_can_change_or_delete_evidence(tmp_path):
    lines = _grants(tmp_path)
    for user in ("cafe_fas", "cafe_admin", "cafe_logger", "cafewifi"):
        mine = [l for l in lines if l.startswith("GRANT") and f"'{user}'@" in l]
        assert mine, user
        assert not any(".* TO" in l for l in mine), f"{user} ต้องได้สิทธิ์รายตาราง ไม่ใช่ทั้งฐาน"
        for l in mine:
            privs, table = l[6:l.index(" ON ")], l.split("`.`")[-1].split("`")[0] if "`.`" in l else "*"
            if table in ("conn_log", "dns_log", "log_seal"):
                assert "UPDATE" not in privs and "DELETE" not in privs, l
            if table == "audit_log":
                assert "DELETE" not in privs, l
                if "UPDATE" in privs:
                    assert user == "cafe_admin", "แก้ audit ได้เฉพาะปุ่มล้างข้อมูลของแอดมิน (trigger จำกัดแถว > 180 วัน)"


def test_only_ops_can_purge_logs_and_every_user_is_revoked_first(tmp_path):
    lines = _grants(tmp_path)
    ops = [l for l in lines if l.startswith("GRANT") and "'cafe_ops'@" in l]
    assert ops and all("DELETE" in l and ".* TO" in l for l in ops)
    users = {l.split("'")[1] for l in lines if l.startswith("GRANT")}
    for u in users:
        first_grant = next(i for i, l in enumerate(lines) if l.startswith("GRANT") and f"'{u}'@" in l)
        revoke = next(i for i, l in enumerate(lines) if l.startswith("REVOKE ALL") and f"'{u}'@" in l)
        assert revoke < first_grant, f"{u}: REVOKE ก่อน GRANT (รันซ้ำแล้วสิทธิ์ที่เอาออกต้องหายจริง)"
    assert lines[-1] == "FLUSH PRIVILEGES;"


def test_logger_can_only_insert_traffic_logs(tmp_path):
    lines = _grants(tmp_path)
    conn = [l for l in lines if "'cafe_logger'@" in l and "`conn_log`" in l]
    assert conn and all(l.startswith("GRANT INSERT ON") for l in conn)


@pytest.mark.parametrize("unit_name,env", [
    ("cafe-fas.service", "fas"), ("cafe-admin.service", "admin"), ("cafe-logger.service", "logger"),
    ("cafe-bypass-detect.service", "logger"), ("cafe-maintenance.service", "ops"),
    ("cafe-check-disk.service", "ops"), ("cafe-enforce.service", "ops"), ("cafe-reconcile.service", "ops"),
])
def test_each_service_loads_its_own_db_credentials_after_secrets(services, unit_name, env):
    u = unit(services, unit_name)
    sec = u.index("EnvironmentFile=/etc/cafe-wifi/secrets.env")
    own = u.index(f"EnvironmentFile=/etc/cafe-wifi/db/{env}.env")
    assert own > sec, "ไฟล์ของ service ต้องมาทีหลัง จะได้ทับ DB_USER/DB_PASS ของ secrets.env"


def test_setup_database_no_longer_grants_whole_database_to_app_user():
    src = (REPO / "install.sh").read_text(encoding="utf-8")
    body = src[src.index("setup_database() {"):]
    body = body[:body.index("\n}\n")]
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON" not in body
    assert "setup_db_users" in body


def test_install_sh_has_no_carriage_returns():
    """6372a8a: สคริปต์แก้ไฟล์บน Windows ใส่ CR ติดมา -> bash บน Pi `syntax error near unexpected token $'{\r'`"""
    assert b"\r" not in (REPO / "install.sh").read_bytes()


def test_legacy_user_is_restricted_only_after_services_restart(tmp_path):
    """Pi 2026-10-16: ถอดสิทธิ์ user เดิมก่อน restart = logger เขียนไม่ได้ ~45 วิ ทิ้ง 19 รายการ"""
    svc = call(tmp_path, "db_grants_sql svc").stdout
    assert "'cafewifi'@" not in svc and "'cafe_logger'@" in svc
    src = (REPO / "install.sh").read_text(encoding="utf-8")
    start = src[src.index("start_services() {"):]
    start = start[:start.index("\n}\n")]
    assert start.index("restart cafe-logger") < start.index("db_restrict_legacy_user")
    setup = src[src.index("setup_db_users() {"):]
    setup = setup[:setup.index("\n}\n")]
    assert "db_grants_sql svc | mysql" in setup and 'mysql < "${DB_SVC_ENV_DIR}/grants.sql"' not in setup
