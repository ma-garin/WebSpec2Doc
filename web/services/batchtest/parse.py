"""スクリプトの読み取り。実行せず、文字列の規則だけで引数・終了コード・入出力・環境変数を抜き出す。

対象: Windows バッチ（.bat / .cmd）・シェル（.sh）・PowerShell（.ps1）。
読み取れなかったものは空のまま返し、推測で埋めない（ケース設計側で「要確認」にする）。
"""
from __future__ import annotations

import re
from pathlib import Path

DIALECTS = {".bat": "cmd", ".cmd": "cmd", ".sh": "sh", ".ps1": "pwsh"}

# 実行環境が最初から持つ変数。これらは「利用者が用意する環境変数」に数えない
_BUILTIN = {
    "cmd": {"DATE", "TIME", "CD", "ERRORLEVEL", "RANDOM", "COMPUTERNAME", "USERNAME", "USERPROFILE",
            "PATH", "TEMP", "TMP", "CMDCMDLINE", "OS", "PROCESSOR_ARCHITECTURE", "SYSTEMROOT", "WINDIR",
            "PATHEXT", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "HOMEDRIVE", "HOMEPATH", "COMSPEC"},
    "sh": {"HOME", "PATH", "PWD", "USER", "SHELL", "IFS", "RANDOM", "LINENO", "OLDPWD", "TMPDIR",
           "HOSTNAME", "BASH_SOURCE", "SECONDS", "PPID", "UID", "LANG", "LC_ALL", "TZ"},
    "pwsh": {"PATH", "TEMP", "USERNAME", "COMPUTERNAME", "USERPROFILE", "APPDATA"},
}

_FORMATS = (
    (re.compile(r"(?i)(yyyymmdd|ymd|date|日付)"), "yyyymmdd"),
    (re.compile(r"(?i)(yyyymm|^ym$|_ym$|^ym_|yearmonth|month|年月)"), "yyyymm"),
)
_LOG = re.compile(r"(?i)\.log\b|[\\/]logs?[\\/]")
_LOCK = re.compile(r"(?i)\.lock\b|\.pid\b|lock")
_DRY = re.compile(r"(?i)dry|whatif|simulate|check|test")


def dialect_of(name: str) -> str:
    return DIALECTS.get(Path(name).suffix.lower(), "sh")


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp932", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _fmt(name: str) -> str | None:
    for pat, fmt in _FORMATS:
        if pat.search(name):
            return fmt
    return None


def _clean(path: str) -> str:
    return path.strip().strip('"\'').rstrip(";)").strip()


def _comment(line: str, dialect: str) -> str:
    s = line.strip()
    if dialect == "cmd":
        m = re.match(r"(?i)^(?:rem\b|::)\s*(.*)", s)
    else:
        m = re.match(r"^#\s*(.*)", s)
    return m.group(1).strip() if m else ""


def _message(line: str) -> str:
    m = re.search(r"(?i)\b(?:echo|write-(?:error|host|output|warning)|printf)\b\s*(?:-\w+\s+)?(.*)", line)
    if not m:
        return ""
    text = re.sub(r"\s*(\d?>&\d|\d?>>?\s*\S+)\s*$", "", m.group(1)).strip().strip('"\'')
    return text[:80]


def _meaning(lines: list[str], idx: int, dialect: str) -> str:
    """exit の直前 3 行から、意味を表す文（echo の文言かコメント）を拾う。"""
    for j in range(idx, max(-1, idx - 4), -1):
        line = lines[j]
        msg = _message(line) or _comment(line, dialect)
        if msg:
            return msg
    return ""


def _expand(path: str, assigns: dict[str, str]) -> str:
    """%VAR% / ${VAR} / $VAR を、スクリプト内で代入した値に置き換える（2 段まで）。"""
    for _ in range(2):
        path = re.sub(r"%(\w+)%|\$\{(\w+)\}|\$(\w+)",
                      lambda m: assigns.get((m.group(1) or m.group(2) or m.group(3)).upper(), m.group(0)), path)
    return path


def _looks_like_file(path: str) -> bool:
    return bool(re.search(r"\.\w{2,4}$", path)) and not path.startswith("-")


def _add(items: list[dict], key: str, value: str, line_no: int, **extra) -> None:
    if value and not any(i[key] == value for i in items):
        items.append({key: value, "line": line_no, **extra})


def analyze(text: str, name: str) -> dict:
    dialect = dialect_of(name)
    lines = text.splitlines()
    facts: dict = {"script": name, "dialect": dialect, "lines": len(lines), "args": [], "flags": [],
                   "exit_codes": [], "inputs": [], "outputs": [], "logs": [], "env_vars": [], "lock": None}
    assigned: set[str] = set()
    assigns: dict[str, str] = {}
    flag_pos: set[int] = set()
    arg_names: dict[int, str] = {}
    required: dict[int, int] = {}
    for i, line in enumerate(lines):
        n = i + 1
        s = line.strip()
        if not s or _comment(line, dialect) and not re.search(r"\bexit\b", s, re.I):
            continue
        if dialect == "cmd":
            for m in re.finditer(r'(?i)\bset\s+"?(\w+)=%~?(\d)', s):
                arg_names[int(m.group(2))] = m.group(1)
            for m in re.finditer(r"(?i)\bset\s+(?:/[ap]\s+)?\"?(\w+)=([^\"]*)", s):
                assigned.add(m.group(1).upper())
                if not re.match(r"%~?\d", m.group(2)):  # 引数の別名は展開しない（{YM} のまま残す）
                    assigns[m.group(1).upper()] = m.group(2).strip()
            for m in re.finditer(r"%~?(\d)", s):
                arg_names.setdefault(int(m.group(1)), "")
            if re.search(r'(?i)if\s+(?:"%~?\d"\s*==\s*""|\[%~?\d\]\s*==\s*\[\])', s):
                required[int(re.search(r"%~?(\d)", s).group(1))] = n
            for m in re.finditer(r'(?i)if\s+(?:/i\s+)?"?%~?(\d)"?\s*==\s*"?([-/][\w-]+)"?', s):
                _add(facts["flags"], "name", m.group(2), n)
                flag_pos.add(int(m.group(1)))
            for m in re.finditer(r"%(\w+)%", s):
                var = m.group(1).upper()
                if var not in assigned and var not in _BUILTIN["cmd"] and not var.isdigit():
                    _add(facts["env_vars"], "name", m.group(1), n,
                         required=bool(re.search(r"(?i)if\s+not\s+defined\s+" + m.group(1), s)))
            for m in re.finditer(r"(?i)if\s+not\s+defined\s+(\w+)", s):
                _add(facts["env_vars"], "name", m.group(1), n, required=True)
            code = re.search(r"(?i)\bexit\s+(?:/b\s+)?(\d+)\b", s)
            in_pat = r'(?i)(?:if\s+not\s+exist|\btype|for\s+/f\b.*?\bin\s*\()\s+"?([^\s"()]+)"?|<\s*"?([^\s"]+)'
        elif dialect == "sh":
            for m in re.finditer(r'(\w+)=["\']?\$\{?(\d)', s):
                arg_names[int(m.group(2))] = m.group(1)
            for m in re.finditer(r"(?:^|\s|;)(?:export\s+|local\s+|readonly\s+)?(\w+)=(\S*)", s):
                assigned.add(m.group(1))
                if not re.match(r"[\"']?\$\{?\d", m.group(2)):
                    assigns[m.group(1).upper()] = m.group(2).strip('"\'')
            for m in re.finditer(r"\$\{?(\d)", s):
                if m.group(1) != "0":
                    arg_names.setdefault(int(m.group(1)), "")
            if re.search(r'\[\[?\s*-z\s+"?\$\{?\d', s) or re.search(r"\$#\s*-(?:lt|eq)\s*\d", s):
                pos = re.search(r"\$\{?(\d)", s)
                required[int(pos.group(1)) if pos else 1] = n
            for m in re.finditer(r'\$\{?(\d)\}?"?\s*==?\s*"?(--?[a-z][\w-]*)"?', s):
                _add(facts["flags"], "name", m.group(2), n)
                flag_pos.add(int(m.group(1)))
            for m in re.finditer(r'^\s*"?(--?[a-z][\w-]*)"?\)', s):  # case 文の分岐
                _add(facts["flags"], "name", m.group(1), n)
            for m in re.finditer(r"\$\{?([A-Z_][A-Z0-9_]*)", s):
                var = m.group(1)
                if var not in assigned and var not in _BUILTIN["sh"]:
                    _add(facts["env_vars"], "name", var, n, required=bool(re.search(r":\?|-z\s+\"?\$\{?" + var, s)))
            code = re.search(r"\bexit\s+(\d+)\b", s)
            in_pat = r'(?:\[\[?\s*!\s*-[fe]\s+|\bcat\s+|<\s*)"?([^\s"\];]+)"?'
        else:
            pm = re.search(r"(?i)(\[Parameter\([^)]*Mandatory[^)]*\)\])?\s*\[(\w+)\]\s*\$(\w+)", s)
            if pm and pm.group(2).lower() != "switch" and (pm.group(1) or "param" in text[:400].lower()):
                idx = len(arg_names) + 1
                arg_names[idx] = pm.group(3)
                if pm.group(1):
                    required[idx] = n
            sw = re.search(r"(?i)\[switch\]\s*\$(\w+)", s)
            if sw:
                _add(facts["flags"], "name", "-" + sw.group(1), n)
            for m in re.finditer(r"(?i)\$env:(\w+)", s):
                _add(facts["env_vars"], "name", m.group(1), n,
                     required=bool(re.search(r"(?i)if\s*\(\s*-not\s+\$env:" + m.group(1), s)))
            code = re.search(r"(?i)\bexit\s+(\d+)\b", s)
            in_pat = r'(?i)(?:Test-Path|Get-Content|Import-Csv)\s+(?:-\w+\s+)?"?([^\s"\)]+)"?'
        if code:
            meaning = "正常終了" if code.group(1) == "0" else _meaning(lines, i, dialect)
            hit = next((c for c in facts["exit_codes"] if c["code"] == code.group(1)), None)
            if hit is None:
                facts["exit_codes"].append({"code": code.group(1), "line": n, "meaning": meaning,
                                            "meanings": [{"text": meaning, "line": n}]})
            else:
                hit["meanings"].append({"text": meaning, "line": n})
        for m in re.finditer(in_pat, s):
            target = _expand(_clean(next(g for g in m.groups() if g)), assigns)
            if not _looks_like_file(target) or _LOCK.search(target):
                continue
            _add(facts["logs"] if _LOG.search(target) else facts["inputs"], "path", target, n)
        out_pat = r'(?i)(>>?)\s*"?([^\s"&|>]+)"?' if dialect != "pwsh" else \
            r'(?i)(Out-File|Set-Content|Add-Content|Export-Csv)\s+(?:-\w+\s+)?"?([^\s"\)]+)"?'
        for m in re.finditer(out_pat, s):
            op, target = m.group(1), _expand(_clean(m.group(2)), assigns)
            if target.lower() in ("nul", "/dev/null", "&2", "&1", "$null") or target.startswith("&") or not target:
                continue
            if _LOCK.search(target):
                facts["lock"] = facts["lock"] or {"path": target, "line": n}
            elif _LOG.search(target) or op in (">>", "Add-Content"):
                _add(facts["logs"], "path", target, n)
            else:
                _add(facts["outputs"], "path", target, n)
        lk = re.search(r'(?i)(?:if\s+exist|-[fe])\s+"?([^\s"\]]*lock[^\s"\]]*)"?', s)
        if lk and not facts["lock"]:
            facts["lock"] = {"path": _clean(lk.group(1)), "line": n}
    facts["args"] = [
        {"pos": pos, "name": arg_names[pos] or f"引数{pos}", "required": pos in required,
         "line": required.get(pos), "format": _fmt(arg_names[pos] or "")}
        for pos in sorted(arg_names) if 1 <= pos <= 9 and not (pos in flag_pos and not arg_names[pos])
    ]
    for f in facts["flags"]:
        f["pos"] = min(flag_pos) if flag_pos else None
    for f in facts["flags"]:
        f["dry_run"] = bool(_DRY.search(f["name"]))
    # 引数として読み取った変数は環境変数に数えない
    names = {a["name"].upper() for a in facts["args"]}
    facts["env_vars"] = [e for e in facts["env_vars"] if e["name"].upper() not in names]
    return facts


def default_command(facts: dict) -> str:
    """起動コマンドの雛形。引数は {名前} の形で置く。"""
    script = facts["script"]
    head = {"cmd": script, "sh": f"bash {script}", "pwsh": f"pwsh -File {script}"}[facts["dialect"]]
    args = " ".join("{" + a["name"] + "}" for a in facts["args"])
    return f"{head} {args}".strip()
