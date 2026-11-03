# -*- coding: utf-8 -*-
import os, json, hashlib, sys

root = os.path.dirname(os.path.abspath(__file__))
man = json.load(open(os.path.join(root, "01-manifest.json"), encoding="utf-8"))
bad = []
for it in man["files"]:
    p = os.path.join(root, it["path"])
    if not os.path.isfile(p):
        bad.append((it["path"], "MISSING"))
        continue
    h = hashlib.md5(open(p, "rb").read()).hexdigest()
    if h != it["md5"]:
        bad.append((it["path"], "MD5"))
print(f"清单 {man['file_count']} 个文件；异常 {len(bad)}")
for b in bad[:20]:
    print("  ✗", b)
sys.exit(0 if not bad else 1)
