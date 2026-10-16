---
name: windows-crlf-edit-trap
description: Editing repo files from Python on this Windows laptop can inject CR into install.sh and break bash on the Pi; how to edit/deploy safely
metadata:
  node_type: memory
  type: feedback
  originSessionId: 5d3fd741-97ba-4504-a0b7-ff3d7e36894a
  modified: 2026-10-16T05:57:59.311Z
---

Repo has `core.autocrlf=true` + `.gitattributes` `* text=auto eol=lf`, so working copies are often CRLF.
A Python one-off edit (`io.open(p,'w')` on Windows, or re-joining with '\r\n') wrote stray CRs into
install.sh; git then classified it `-text` and committed the CRs (6372a8a). On the Pi:
`syntax error near unexpected token $'{\r'`. Fixed in the next commit + `test_install_sh_has_no_carriage_returns`.

**Why:** cost a failed install run on the lab Pi (2026-10-16); python files with CRLF still run, so only .sh breaks loudly.

**How to apply:**
- Prefer the Edit tool. If scripting, open with `newline=''` and keep the file's own line ending; for .sh strip `\r`.
- Check before commit: `git ls-files --eol | grep -v i/lf` (only .gitattributes is expected there).
- Deploy to the Pi from git, not the working tree: `git archive HEAD ... | scp` (LF guaranteed). git archive gives 0664 files — install.sh now strips group-write (`find -perm /022 -exec chmod go-w`).
- With `ssh ... 'a && b; c'` the `;` still runs `c` after a failure — use `set -e` in remote scripts.

Related: [[pi-image-ssh-access]]
