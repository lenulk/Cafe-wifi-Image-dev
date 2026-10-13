"""
docs/build_word.py — รวมเอกสารใน docs/ เป็นไฟล์ Word + PDF ไฟล์เดียว (ต้องมี Microsoft Word บนเครื่อง)

    pip install markdown pywin32 playwright
    python docs/build_word.py            # ได้ รายงานเล่ม/เอกสารระบบ-Cafe-WiFi.docx และ .pdf

ขั้นตอน: markdown -> HTML ก้อนเดียว (ลิงก์ข้ามเอกสารกลายเป็นลิงก์ภายใน, mermaid เรนเดอร์เป็นภาพด้วย
Playwright) -> เปิดใน Word ผ่าน COM -> ใส่ปก/สารบัญ/เลขหน้า/ฟอนต์ไทย -> บันทึก .docx + export .pdf
"""
from __future__ import annotations

import hashlib
import html
import re
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT_DIR = ROOT / "รายงานเล่ม"
OUT_NAME = "เอกสารระบบ-Cafe-WiFi"
BUILD = ROOT / "docs" / ".build"

# ลำดับบทในเล่ม (ไฟล์ที่ไม่อยู่ในรายการนี้ไม่ถูกรวม เช่น hardware-test-log ที่เป็นหลักฐานยาว)
PARTS = [
    ("ภาคที่ 1 ภาพรวมระบบ", ["architecture"]),
    ("ภาคที่ 2 การติดตั้ง", ["install-from-image", "isp-router-runbook", "backup-usb"]),
    ("ภาคที่ 3 การใช้งานและดูแลระบบ", ["admin-guide", "operations"]),
    ("ภาคที่ 4 เอกสารอ้างอิง", ["configuration", "database", "cli-tools"]),
    ("ภาคที่ 5 การพัฒนาและทดสอบ", ["developer-guide", "docker-test", "test-plan"]),
    ("ภาคผนวก", ["privacy-policy-th"]),
]

FONT = "TH Sarabun New"
MONO = "Consolas"


def bm(*parts: str) -> str:
    """ชื่อ bookmark ของ Word: ตัวอักษรอังกฤษ/ตัวเลข ≤ 40 ตัว"""
    return "b" + hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def gh_slug(text: str) -> str:
    """slug แบบ GitHub (ใช้ตรงกับลิงก์ #anchor ที่เขียนไว้ในเอกสาร)"""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ฀-๿]", "", text)
    return text.replace(" ", "-")


def render_mermaid(blocks: list[str], tag: str) -> list[Path]:
    if not blocks:
        return []
    from playwright.sync_api import sync_playwright
    outs = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        for i, src in enumerate(blocks):
            page.set_content(
                "<html><body style='margin:0;background:#fff'><pre class='mermaid'>"
                + html.escape(src) + "</pre>"
                "<script src='https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js'></script>"
                "<script>mermaid.initialize({startOnLoad:true,theme:'neutral',"
                "fontFamily:'Tahoma'});</script></body></html>")
            page.wait_for_selector("pre.mermaid svg", timeout=30000)
            out = BUILD / f"mermaid-{tag}-{i}.png"
            page.locator("pre.mermaid svg").screenshot(path=str(out))
            outs.append(out)
        browser.close()
    return outs


def convert_doc(name: str, chapter: int) -> str:
    md_text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
    # สารบัญย่อยของแต่ละไฟล์ซ้ำกับสารบัญรวมของเล่ม -> ตัดออก
    md_text = re.sub(r"^#{2,3} สารบัญ[^\n]*\n.*?(?=^#{1,6} )", "", md_text, count=1,
                     flags=re.M | re.S)
    md_text = re.sub(r"^\*\*สารบัญ\*\*\n(?:\d+\..*\n)+", "", md_text, flags=re.M)

    # mermaid -> ภาพ
    blocks = re.findall(r"```mermaid\n(.*?)```", md_text, flags=re.S)
    for i, png in enumerate(render_mermaid(blocks, name)):
        md_text = md_text.replace(f"```mermaid\n{blocks[i]}```",
                                  f"![แผนภาพ]({png.as_uri()})", 1)

    # ภาพที่อ้างแบบ relative -> absolute
    def img(m):
        alt, src = m.group(1), m.group(2)
        if src.startswith("file:"):
            return m.group(0)
        return f"![{alt}]({(DOCS / src).resolve().as_uri()})"
    md_text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", img, md_text)

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])

    # หัวข้อ: ภาค = h1 · ชื่อไฟล์ (h1 เดิม) = h2 "บทที่ n" · หัวข้ออื่นเลื่อนลงหนึ่งระดับ
    first = [True]

    def head(m):
        level, inner = int(m.group(1)), m.group(2)
        anchor = f'<a name="{bm(name, gh_slug(inner))}"></a>'
        if level == 1 and first[0]:
            first[0] = False
            return f'<h2><a name="{bm(name)}"></a>{anchor}บทที่ {chapter} {inner}</h2>'
        lv = min(level + 1, 6)
        return f"<h{lv}>{anchor}{inner}</h{lv}>"
    body = re.sub(r"<h([1-6])>(.*?)</h\1>", head, body, flags=re.S)

    # ลิงก์: เอกสารในเล่ม -> ลิงก์ภายใน · ไฟล์ในรีโป -> ข้อความ · http คงไว้
    included = {n for _, ns in PARTS for n in ns}

    def link(m):
        href, text = html.unescape(m.group(1)), m.group(2)
        if href.startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        if href.startswith("#"):
            return f'<a href="#{bm(name, href[1:])}">{text}</a>'
        path, _, frag = href.partition("#")
        target = Path(path).stem
        if path.endswith(".md") and "/" not in path and target in included:
            dest = bm(target, frag) if frag else bm(target)
            return f'<a href="#{dest}">{text}</a>'
        return text  # ไฟล์โค้ดในรีโป ไม่มีในเล่ม
    body = re.sub(r'<a href="([^"]*)">(.*?)</a>', link, body, flags=re.S)
    return body


def cover_html() -> str:
    c = "#5C3A2B"
    return f"""
<p style="text-align:center;margin-top:200pt;font-size:30pt;font-weight:bold;color:{c}">เอกสารระบบ</p>
<p style="text-align:center;font-size:42pt;font-weight:bold;color:{c}">Cafe-WiFi OS</p>
<p style="text-align:center;margin-top:14pt;font-size:17pt">ระบบ Wi-Fi ร้านกาแฟ: captive portal ลงทะเบียนด้วยบัตรประชาชน
+ พนักงานอนุมัติ + เก็บข้อมูลจราจรทางคอมพิวเตอร์ตาม พ.ร.บ.คอมพิวเตอร์ฯ มาตรา 26</p>
<p style="text-align:center;margin-top:140pt;font-size:16pt">{version()}</p>
<p style="text-align:center;font-size:16pt">ฉบับวันที่ {thai_date()}</p>
<p style="page-break-before:always;font-size:26pt;font-weight:bold;color:{c}">สารบัญ</p>
<p>TOC_PLACEHOLDER</p>
"""


def thai_date() -> str:
    import datetime
    d = datetime.date.today()
    months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม",
              "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"{d.day} {months[d.month - 1]} {d.year + 543}"


def build_html() -> Path:
    BUILD.mkdir(exist_ok=True)
    chunks, chapter = [cover_html()], 0
    for part, names in PARTS:
        chunks.append('<p style="page-break-before:always">&nbsp;</p>'
                      + '<p>&nbsp;</p>' * 9 + f"<h1>{part}</h1>")
        for n in names:
            chapter += 1
            chunks.append(convert_doc(n, chapter))
    css = f"""
    body {{ font-family: '{FONT}'; font-size: 15pt; }}
    pre, code {{ font-family: '{MONO}'; font-size: 8pt; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border: 1px solid #999; padding: 2px 4px; font-size: 13pt; vertical-align: top; }}
    th {{ background: #e8e2d8; }}
    img {{ max-width: 15cm; }}
    """
    doc = (f"<html><head><meta charset='utf-8' /><style>{css}</style></head><body>"
           + "\n".join(chunks) + "</body></html>")
    out = BUILD / "combined.html"
    out.write_text(doc, encoding="utf-8")
    return out


def version() -> str:
    v = (ROOT / "image" / "VERSION").read_text().strip()
    try:
        h = subprocess.check_output(["git", "-C", str(ROOT), "log", "-1", "--format=%h"],
                                    text=True).strip()
    except Exception:
        h = "?"
    return f"เวอร์ชัน {v} · commit {h}"


def word_pass(html_path: Path) -> None:
    import win32com.client as win32

    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = word.Documents.Open(str(html_path), ConfirmConversions=False, ReadOnly=False,
                              Format=7)  # wdOpenFormatWebPages
    try:
        word.ActiveWindow.View.Type = 3  # wdPrintView
        cm = 28.3465
        ps = doc.PageSetup
        ps.PaperSize = 7  # wdPaperA4
        ps.TopMargin = ps.BottomMargin = 2.2 * cm
        ps.LeftMargin = 2.5 * cm
        ps.RightMargin = 2.0 * cm
        maxw = ps.PageWidth - ps.LeftMargin - ps.RightMargin
        brown = 0x2B3A5C  # BGR ของ #5C3A2B

        def style(sid, size, bold=False, color=None, before=None, after=None):
            s = doc.Styles(sid)
            f = s.Font
            f.Name = f.NameAscii = f.NameOther = f.NameBi = FONT
            f.Size = f.SizeBi = size
            f.Bold = f.BoldBi = bold
            if color is not None:
                f.Color = color
            if before is not None:
                s.ParagraphFormat.SpaceBefore = before
            if after is not None:
                s.ParagraphFormat.SpaceAfter = after
            return s

        style(-1, 15, after=4)                                          # Normal
        h1 = style(-2, 34, True, brown, before=0, after=0)            # ภาค
        h1.ParagraphFormat.Alignment = 1
        h1.ParagraphFormat.PageBreakBefore = False
        style(-3, 24, True, brown, before=0, after=10)                   # บท
        doc.Styles(-3).ParagraphFormat.PageBreakBefore = True
        style(-4, 19, True, brown, before=14, after=4)
        style(-5, 16, True, brown, before=10, after=2)
        style(-6, 15, True, brown, before=8, after=2)
        style(-7, 15, True, brown, before=6, after=2)

        # ภาษาไทยใช้ฟอนต์ complex script -> ตั้งทั้งเล่ม (ไม่งั้นตกเป็นฟอนต์อื่นในตาราง)
        doc.Content.Font.NameBi = FONT

        pre_name = doc.Styles(-102).NameLocal  # wdStyleHtmlPre (ชื่อเปลี่ยนตามภาษา UI ของ Word)

        def is_pre(p):
            try:
                return p.Style.NameLocal == pre_name
            except Exception:
                return False

        # inline code (Consolas) ให้ขนาดกลืนกับเนื้อความ
        f = doc.Content.Find
        f.ClearFormatting()
        f.Font.Name = MONO
        f.Text = ""
        f.Format = True
        f.Replacement.ClearFormatting()
        f.Replacement.Font.Size = 10.5
        f.Execute(Replace=2)  # wdReplaceAll

        for p in doc.Paragraphs:
            if is_pre(p):
                r = p.Range
                r.Font.Name = MONO
                r.Font.Size = 8
                r.Font.SizeBi = 10
                r.ParagraphFormat.SpaceAfter = 0
                r.ParagraphFormat.SpaceBefore = 0
                r.ParagraphFormat.LineSpacingRule = 0
                r.ParagraphFormat.LeftIndent = 0.3 * cm
                r.Shading.BackgroundPatternColor = 0xF4F4F4

        # ตาราง: เต็มความกว้างหน้า ไม่ล้นขอบ หัวตารางซ้ำทุกหน้า
        for t in doc.Tables:
            t.Range.Font.Size = 13
            t.Range.Font.SizeBi = 13
            t.Range.ParagraphFormat.SpaceAfter = 0
            t.Range.ParagraphFormat.SpaceBefore = 0
            rf = t.Range.Find
            rf.ClearFormatting()
            rf.Font.Name = MONO
            rf.Text = ""
            rf.Format = True
            rf.Replacement.ClearFormatting()
            rf.Replacement.Font.Size = 9
            rf.Execute(Replace=2)
            t.AllowAutoFit = True
            t.AutoFitBehavior(1)  # ตามเนื้อหา
            t.AutoFitBehavior(2)  # เต็มหน้า
            t.PreferredWidthType = 2  # เปอร์เซ็นต์
            t.PreferredWidth = 100
            t.Rows.AllowBreakAcrossPages = True
            t.TopPadding = t.BottomPadding = 1
            t.LeftPadding = t.RightPadding = 3
            try:
                t.Rows(1).HeadingFormat = True
            except Exception:
                pass
            # ถ้ายังกว้างเกินหน้า (สตริงยาวไม่มีช่องว่าง) บีบคอลัมน์ตามสัดส่วนแล้วล็อก
            try:
                widths = [col.Width for col in t.Columns]
                total = sum(widths)
                if total > maxw + 1:
                    t.AutoFitBehavior(0)  # fixed
                    for col, w in zip(t.Columns, widths):
                        col.Width = w * maxw / total
            except Exception:
                pass  # ตารางที่มีเซลล์ผสาน

        # ภาพ: ฝังในไฟล์ และไม่เกินความกว้างหน้า
        for sh in doc.InlineShapes:
            try:
                sh.LinkFormat.SavePictureWithDocument = True
                sh.LinkFormat.BreakLink()
            except Exception:
                pass
            if sh.Type == 6:  # wdInlineShapeHorizontalLine (จาก ---)
                continue
            sh.LockAspectRatio = True
            if (sh.AlternativeText or "").startswith("แผนภาพ"):
                sh.Width = maxw * 0.95
            if sh.Width > maxw * 0.9:
                sh.Width = maxw * 0.9
            if sh.Height > 11 * cm:
                sh.Height = 11 * cm

        # สารบัญ
        f = doc.Content.Find
        f.ClearFormatting()
        f.Text = "TOC_PLACEHOLDER"
        if f.Execute():
            rng = f.Parent
            rng.Text = ""
            doc.TablesOfContents.Add(rng, True, 1, 3)

        # หัว/ท้ายกระดาษ (ไม่แสดงบนปก)
        sec = doc.Sections(1)
        sec.PageSetup.DifferentFirstPageHeaderFooter = True
        footer = sec.Footers(1)
        footer.PageNumbers.Add(1, True)
        footer.Range.Font.Name = footer.Range.Font.NameBi = FONT
        hdr = sec.Headers(1).Range
        hdr.Text = "Cafe-WiFi OS — เอกสารระบบ"
        hdr.Font.Name = hdr.Font.NameBi = FONT
        hdr.Font.Size = hdr.Font.SizeBi = 12
        hdr.Font.Color = 0x808080
        hdr.ParagraphFormat.Alignment = 2

        toc = doc.TablesOfContents(1)
        toc.Update()
        # สไตล์บรรทัดสารบัญ
        for sid, size, bold in ((-20, 16, True), (-21, 15, False), (-22, 14, False)):  # TOC 1-3
            s = doc.Styles(sid)
            s.Font.Name = s.Font.NameBi = FONT
            s.Font.Size = s.Font.SizeBi = size
            s.Font.Bold = s.Font.BoldBi = bold
            s.ParagraphFormat.SpaceAfter = 0
            s.ParagraphFormat.SpaceBefore = 6 if sid == -20 else 0
        toc.Update()

        OUT_DIR.mkdir(exist_ok=True)
        docx = OUT_DIR / f"{OUT_NAME}.docx"
        pdf = OUT_DIR / f"{OUT_NAME}.pdf"
        doc.SaveAs2(str(docx), FileFormat=16)  # wdFormatDocumentDefault
        doc.ExportAsFixedFormat(str(pdf), 17, OpenAfterExport=False,
                                OptimizeFor=0, CreateBookmarks=1)  # PDF + bookmark จากหัวข้อ
        print(docx)
        print(pdf, doc.ComputeStatistics(2), "pages")
    finally:
        doc.Close(False)
        word.Quit()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    word_pass(build_html())
