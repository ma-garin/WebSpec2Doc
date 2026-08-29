#!/usr/bin/env python3
"""T05 D08 _safe_reference_doc_paths unit tests (no tenant context → OUTPUT_DIR)."""
import os, sys, json
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.join(os.getcwd(),"src"))
from web.validation import _safe_reference_doc_paths
from web.config import OUTPUT_DIR
DOM="127.0.0.1:9105"
base=os.path.join(str(OUTPUT_DIR), DOM, "reference_docs")
good=os.path.join(base,"ref_good.md")
cases={
 "C034_valid":[good],
 "C035_dotdot":[os.path.join(base,"..","..","x.md")],
 "C036_otherdomain":[os.path.join(str(OUTPUT_DIR),"127.0.0.1:9199","reference_docs","x.md")],
 "C037_missing":[os.path.join(base,"does_not_exist_zzz.md")],
 "C038_abs_etc":["/etc/hosts"],
 "C039m_mixed":[good, os.path.join(base,"..","..","x.md"), os.path.join(str(OUTPUT_DIR),"other.example","reference_docs","x.md")],
}
out={}
for k,v in cases.items():
    r=_safe_reference_doc_paths(v, DOM)
    out[k]={"input":v,"accepted":r}
    print(k, "ACCEPTED:", r)
# C065: valid path then remove the underlying file → should be excluded (missing_file)
tmpname=os.path.join(base,"to_be_removed.md")
open(tmpname,"w").write("# tmp\n")
r_before=_safe_reference_doc_paths([tmpname],DOM)
os.remove(tmpname)
r_after=_safe_reference_doc_paths([tmpname],DOM)
out["C065"]={"before":r_before,"after":r_after}
print("C065 before:",r_before,"after:",r_after)
# invalid domain
out["C_invdom"]={"result":_safe_reference_doc_paths([good],"../evil")}
print("invalid-domain:", out["C_invdom"]["result"])
json.dump(out, open(os.path.join(os.path.dirname(__file__),"..","evidence","outputs","safepath_results.json"),"w"), ensure_ascii=False, indent=1)
