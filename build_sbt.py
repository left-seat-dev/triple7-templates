"""Build the multi-pilot SBT / Manual Handling artifact from a JSON content file.
Usage: python3 build_sbt.py content_s2.json outdir
content_s2.json shape:
{ "session": "P3M1S2", "name": "SBT",
  "pilots": [ {"key": "ca", "label": "CA", "active": ["k","h","m"],
               "content": {"k": "...", "h": "...", "m": "...", "oc": "..."}},
              {"key": "fo", "label": "FO", "active": ["h","p","s"], "content": {...}} ] }
No session data lives in this script or the template - only in the JSON you pass in.
"""
import json, sys, os
content = json.load(open(sys.argv[1], encoding="utf-8"))
outdir = sys.argv[2] if len(sys.argv) > 2 else "."
tpl = open(os.path.join(os.path.dirname(__file__), "Triple7_Report_Template.html"), encoding="utf-8").read()
code, name = content["session"], content.get("name", "SBT")
tpl = tpl.replace("code: 'XXXX',", f"code: '{code}',").replace("name: 'Session',", f"name: '{name}',").replace("filename: 'XXXX_Session'", f"filename: '{code}_{name}'")
def check(text):
    bad = [c for c in text if ord(c) > 126 or (ord(c) < 32 and c != "\n")]
    if bad: raise SystemExit(f"non-keyboard characters in report text: {[hex(ord(c)) for c in bad]}")
pilots = []
for p in content["pilots"]:
    c = {k: p["content"].get(k, "") for k in "khapmsdcl"}
    c["oc"] = p["content"].get("oc", "")
    for v in c.values(): check(v)
    pilots.append({"key": p["key"], "label": p["label"], "active": p["active"], "content": c})
    print(p["label"], {k: len(v.split()) for k, v in c.items() if v})
out = tpl.replace("const PILOTS = [];  // filled by build_sbt.py", "const PILOTS = " + json.dumps(pilots, indent=2, ensure_ascii=True) + ";")
path = os.path.join(outdir, f"{code}_{name}_Report.html")
open(path, "w", encoding="utf-8").write(out)
print(path)
