#!/usr/bin/env python3
"""T05 upload/doc-fusion API tests (curl-free, urllib multipart)."""
import io, json, os, urllib.request, urllib.error, uuid, sys
BASE="http://127.0.0.1:8765"; DOM="127.0.0.1:9105"
FX=os.path.join(os.path.dirname(__file__),"..","evidence","fixtures")
def post_multipart(path, fields, files, domain_raw=None):
    b="----t05-"+uuid.uuid4().hex; body=io.BytesIO()
    def w(s): body.write(s if isinstance(s,bytes) else s.encode())
    for k,v in fields.items():
        w(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
    for fname,data in files:
        w(f"--{b}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{fname}\"\r\n"
          "Content-Type: application/octet-stream\r\n\r\n"); w(data); w("\r\n")
    w(f"--{b}--\r\n")
    req=urllib.request.Request(BASE+path, data=body.getvalue(),
        headers={"Content-Type":f"multipart/form-data; boundary={b}","Origin":BASE})
    try:
        r=urllib.request.urlopen(req,timeout=30); return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
def upload(fname, data, domain=DOM):
    return post_multipart("/api/reference-docs", {"domain":domain}, [(fname,data)])
def rd(n): return open(os.path.join(FX,n),"rb").read()
R=[]
def rec(cid,status,body,note=""):
    R.append({"case":cid,"status":status,"body":body[:300],"note":note})
    print(f"{cid}\t{status}\t{note}\t{body[:160]}")
# C001-C010 happy
rec("C001",*upload("ref_good.md",rd("ref_good.md")))
rec("C002",*upload("note.txt",rd("note.txt")))
rec("C003",*upload("book.xlsx",rd("book.xlsx")))
rec("C004",*upload("data.yaml",rd("data.yaml")))
rec("C005",*upload("data.json",rd("data.json")))
rec("C006",*upload("login.feature",rd("login.feature")))
rec("C007",*upload("tiny.pdf",rd("tiny.pdf")))
rec("C008",*upload("slides.pptx",rd("slides.pptx")))
rec("C009",*upload("upper.MD",rd("upper.MD")))
s,b=post_multipart("/api/reference-docs",{"domain":DOM},[("ref_good.md",rd("ref_good.md")),("note.txt",rd("note.txt"))]); rec("C010",s,b,"multi")
# C011-C016 legacy/unsupported
rec("C011",*upload("x.doc",b"MZ"))
rec("C012",*upload("x.xls",b"MZ"))
rec("C013",*upload("x.ppt",b"MZ"))
rec("C014",*upload("evil.exe",rd("evil.exe")))
rec("C015",*upload("page.html",rd("page.html")))
rec("C016",*upload("noext",rd("noext")))
# C017-C019 size
rec("C017",*upload("empty.md",b""),"0byte")
rec("C018",*upload("big_eq20mb.md",rd("big_eq20mb.md")),"eq20MB")
rec("C019",*upload("big_20mb_plus1.md",rd("big_20mb_plus1.md")),"20MB+1")
# C020 no files
s,b=post_multipart("/api/reference-docs",{"domain":DOM},[]); rec("C020",s,b,"no-files")
# C021-C024 domain
rec("C021",*upload("ref_good.md",b"x",domain=""),"empty-dom")
rec("C022",*upload("ref_good.md",b"x",domain="../evil"),"dotdot-dom")
rec("C023",*upload("ref_good.md",b"x",domain="..%2F..%2Fetc"),"enc-dom")
rec("C024",*upload("ref_good.md",b"x",domain="evil.example"),"other-dom")
# C025-C032 traversal filenames
rec("C025",*upload("../../evil.md",b"# evil\n"),"dotdot-fn")
rec("C026",*upload("..\\evil.md",b"# evil\n"),"backslash-fn")
rec("C027",*upload("/tmp/abs.md",b"# abs\n"),"abs-fn")
rec("C028",*upload("ev\x00il.md",b"# nul\n"),"nul-fn")
rec("C029",*upload("l"*244+".md",b"# long\n"),"long-fn")
# C030 NFC/NFD
import unicodedata
rec("C030a",*upload(unicodedata.normalize("NFC","ガイド.md"),b"# NFC\n"),"nfc")
rec("C030b",*upload(unicodedata.normalize("NFD","ガイド.md"),b"# NFD\n"),"nfd")
# C031 double same-name
rec("C031a",*upload("dup.md",b"# v1\n"),"dup-1")
rec("C031b",*upload("dup.md",b"# v2 changed\n"),"dup-2")
# C032 fake docx
rec("C032",*upload("fake.docx",rd("fake.docx")),"fake-docx")
# C033 mixed batch (valid then invalid)
s,b=post_multipart("/api/reference-docs",{"domain":DOM},[("firstok.md",b"# ok\n"),("evil.exe",b"MZ")]); rec("C033",s,b,"mixed-batch")
# C057-C059 doc-fusion GET
def get(path):
    try:
        r=urllib.request.urlopen(BASE+path,timeout=15); return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
rec("C058",*get("/api/doc-fusion?domain=nodata.example"),"no-run")
rec("C059",*get("/api/doc-fusion?domain=../../etc"),"bad-dom")
json.dump(R, open(os.path.join(os.path.dirname(__file__),"..","evidence","outputs","upload_api_results.json"),"w"), ensure_ascii=False, indent=1)
