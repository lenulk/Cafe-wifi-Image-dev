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
