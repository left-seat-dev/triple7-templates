"""Build one Eval + MT artifact per pilot from a JSON content file.
Usage: python3 build_eval_mt.py content_s1.json outdir
content_s1.json shape:
{ "session": "P3M1S1",
  "pilots": { "CA": { "eval": {"k": {"grade": 4, "text": "..."}, ..., "oc": "..."},
                       "mt": {"status": "OA", "active": ["h","p","c"],
                              "content": {"h": "...", "p": "...", "c": "..."}, "oc": "..."} },
              "FO": { ... } } }
No session data lives in this script or the template - only in the JSON you pass in.
"""
import json, sys, os, re
content = json.load(open(sys.argv[1], encoding="utf-8"))
outdir = sys.argv[2] if len(sys.argv) > 2 else "."
tpl = open(os.path.join(os.path.dirname(__file__), "Eval_MT_Template.html"), encoding="utf-8").read()
code = content["session"]
tpl = tpl.replace("code: 'XXXX',", f"code: '{code}',").replace("filename: 'XXXX_Eval_MT'", f"filename: '{code}_Eval_MT'")
def check(text):
    bad = [c for c in text if ord(c) > 126 or (ord(c) < 32 and c != "\n")]
    if bad: raise SystemExit(f"non-keyboard characters in report text: {[hex(ord(c)) for c in bad]}")
for label, p in content["pilots"].items():
    ev = {c: {"grade": p["eval"].get(c, {}).get("grade"), "text": p["eval"].get(c, {}).get("text", "")} for c in "khapmsdcl"}
    ev["oc"] = p["eval"].get("oc", "")
    mtc = p["mt"].get("content", {})
    mt = {"status": p["mt"].get("status"), "active": p["mt"].get("active", []),
          "content": {c: {"text": mtc.get(c, ""), "rootCause": False} for c in "khapmsdcl"}, "oc": p["mt"].get("oc", "")}
    for c in "khapmsdcl": check(ev[c]["text"]); check(mt["content"][c]["text"])
    check(ev["oc"]); check(mt["oc"])
    pilot = {"key": "p", "label": label, "eval": ev, "mt": mt}
    out = tpl.replace("const PILOT = null;  // filled by build_eval_mt.py", "const PILOT = " + json.dumps(pilot, indent=2, ensure_ascii=True) + ";")
    path = os.path.join(outdir, f"{code}_Eval_MT_{label}.html")
    open(path, "w", encoding="utf-8").write(out)
    words = {c: len(ev[c]["text"].split()) for c in "khapmsdcl"}
    print(label, path, words, "OC", len(ev["oc"].split()))
