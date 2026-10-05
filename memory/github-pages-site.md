---
name: github-pages-site
description: "Product website https://lenulk.github.io/Cafe-wifi-Image/ (live 2026-10-05) — where its source lives, how it deploys, bilingual markup rule, and how to preview locally"
metadata:
  node_type: memory
  type: project
  originSessionId: 0e8e25f0-a0f6-4699-9709-c0d238c30df0
  modified: 2026-10-04T22:39:43.107Z
---

เว็บแนะนำผลิตภัณฑ์ **https://lenulk.github.io/Cafe-wifi-Image/** เปิดใช้ 2026-10-05 (ไทย/EN, โทนร้านกาแฟ, หน้าเดียว + คู่มือติดตั้ง timeline + ส่วน "เราเตอร์ต้องมีอะไรบ้าง")

- **ต้นฉบับอยู่ใน repo งาน** branch `image`: `image/public/site/{index.html,style.css}` + `image/public/pages.yml`
  — ห้ามแก้ตรงใน repo สาธารณะ (จะถูก publish รอบหน้าทับ)
- `publish-public.sh` map `site/*` → `site/` และ `pages.yml` → `.github/workflows/pages.yml`
  ฝั่งสาธารณะ; workflow รวม `site/` + `img/` (รูปชุดเดียวกับ README) แล้ว deploy ด้วย Actions
  (Pages source = GitHub Actions, ไม่ใช้ /docs เพราะ Jekyll จะแปลง docs/*.md และลิงก์ภายในพัง)
- **สองภาษา:** ทุกข้อความเป็นคู่ `<span lang="th">…</span><span lang="en">…</span>` CSS ซ่อนตาม
  `html[data-lang]` — เพิ่มข้อความใหม่ต้องใส่ครบคู่ (ตรวจ: ทุก `[lang=th]` ต้องมี sibling `[lang=en]`)
- เลขรุ่น/ลิงก์ดาวน์โหลด/ขนาดไฟล์ดึงจาก GitHub API releases/latest ตอนเปิดหน้า — ออก release ใหม่ไม่ต้องแก้เว็บ
  แต่ตัวเลขผลทดสอบ (49/49, ~7–8 วิ, ~6 นาที) เขียนตายตัว ต้องแก้มือถ้าผลเปลี่ยน
- ทุกประโยคต้องอ้างผลทดสอบได้ — ผู้ใช้ให้เปลี่ยน "เราเตอร์ค่ายหลายรุ่นไม่มี…" เป็น "บางรุ่นอาจไม่มี…"
  เพราะยังไม่มีผลทดสอบกับเราเตอร์ค่าย · "ใช้กับเราเตอร์เดิมได้" ต้องมี "(ถ้ามีคุณสมบัติครบ)"
- พรีวิวในเครื่อง: copy `site/*` + `image/public/img` ไปโฟลเดอร์เดียวกันแล้ว `python -m http.server`
  (หน้าอ้าง `img/` เทียบกับตัวเอง เปิดจาก `image/public/site/` ตรง ๆ รูปจะหาย)

ดู [[image-installer-plan]], [[push-only-to-own-github]]
