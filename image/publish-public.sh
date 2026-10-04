#!/bin/bash
# image/publish-public.sh -- สร้าง commit สำหรับ repo สาธารณะ (หน้าโชว์ผลิตภัณฑ์) จาก commit ปัจจุบันของ repo งาน
#
# repo งาน (private)  = ทุกอย่าง: ความจำ, เล่ม, แล็บ, ตัว build image
# repo สาธารณะ        = เฉพาะไฟล์ใน ALLOW ข้างล่าง + README/.gitignore จาก image/public/
# ไม่แตะ working tree/branch ปัจจุบัน -- สร้าง commit ด้วย index ชั่วคราว แล้วชี้ branch `public` ไปที่มัน
#
#   bash image/publish-public.sh "ข้อความ commit"     # แล้วตรวจ: git ls-tree -r --name-only public
#   git push public refs/heads/public:refs/heads/main     # ชื่อ branch ชนกับชื่อ remote -- ต้องใช้ ref เต็ม
#
# commit ใหม่ต่อจาก public/main (ถ้ามี) -> ประวัติฝั่งสาธารณะเป็นเส้นของตัวเอง ไม่มี commit ของ repo งานปน
# เพิ่มไฟล์ใหม่ที่ต้องเปิดเผย = แก้ ALLOW ที่นี่ที่เดียว (ไม่มีอะไรหลุดออกไปเองเพราะเป็น allowlist)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
msg=${1:?ใส่ข้อความ commit}

ALLOW=(
  app sql install.sh .gitattributes LICENSE
  tools/__init__.py tools/backup_db.py tools/check_disk.py tools/check_router.py
  tools/enforce_voucher_expiry.py tools/export_evidence.py tools/purge_old_data.py
  tools/reconcile_pending.py tools/reset_admin.py tools/restore_keys.py
  image/VERSION image/prepare-sd.ps1 image/setup
  image/firstboot/cafe-wifi-firstboot.sh image/firstboot/cafe-wifi-firstboot.service
  image/firstboot/cafe-wifi-factory-reset.service
  docs/install-from-image.md docs/backup-usb.md docs/privacy-policy-th.md
)
MAP=(  # ไฟล์ใน repo งาน -> ตำแหน่งใน repo สาธารณะ
  image/public/README.md:README.md
  image/public/gitignore:.gitignore
  image/public/pages.yml:.github/workflows/pages.yml
)

[[ -z $(git status --porcelain -- "${ALLOW[@]}" image/public) ]] || { echo "มีไฟล์ที่จะเผยแพร่ยังไม่ commit" >&2; exit 1; }

export GIT_INDEX_FILE; GIT_INDEX_FILE=$(mktemp)
trap 'rm -f "$GIT_INDEX_FILE"' EXIT
git read-tree --empty
git ls-tree -r HEAD -- "${ALLOW[@]}" | git update-index --index-info
# ภาพหน้าจอของ README (image/public/img/* -> img/*)
while IFS= read -r p; do MAP+=("$p:img/${p##*/}"); done < <(git ls-tree -r --name-only HEAD -- image/public/img)
# หน้าเว็บ GitHub Pages (image/public/site/* -> site/*) -- deploy โดย .github/workflows/pages.yml
while IFS= read -r p; do MAP+=("$p:site/${p#image/public/site/}"); done < <(git ls-tree -r --name-only HEAD -- image/public/site)
for m in "${MAP[@]}"; do
  src=${m%%:*}; dst=${m#*:}
  git update-index --add --cacheinfo "100644,$(git rev-parse "HEAD:$src"),$dst"
done
tree=$(git write-tree)

parent=()
git rev-parse -q --verify refs/remotes/public/main >/dev/null && parent=(-p refs/remotes/public/main)
if [[ ${#parent[@]} -gt 0 && $(git rev-parse "refs/remotes/public/main^{tree}") == "$tree" ]]; then
  echo "ไม่มีอะไรเปลี่ยนจาก public/main"; exit 0
fi
c=$(printf '%s\n\nจาก repo งาน %s\n' "$msg" "$(git rev-parse --short HEAD)" | git commit-tree "$tree" "${parent[@]}")
git branch -f public "$c"
echo "branch public -> $(git rev-parse --short "$c") ($(git ls-tree -r --name-only "$c" | wc -l) ไฟล์)"
