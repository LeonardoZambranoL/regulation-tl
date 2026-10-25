"""Same-page completion: write requirements for candidate clauses (shall + implicit, no tables, operative text) on pages
the submission already cites that were not written yet, and append them. Usage: samepage.py <case> <pred.json> <raw.json> <spec.md> <out.json>"""
import json, sys
from pathlib import Path

R = Path(r"C:\Users\devan\Desktop\Competitions\Hackathon- Certify\regulation-tl\approaches\experiments")
sys.path.insert(0, str(R / "devansh-toolkit" / "src"))
from retrieval.classify import candidates, rationale_pages
from retrieval.write import write

case, pred, raw, specf, outf = sys.argv[1:6]
P = json.load(open(pred, encoding="utf-8"))
W = json.load(open(raw, encoding="utf-8"))["requirements"]
spec = Path(specf).read_text(encoding="utf-8")
start = rationale_pages()
regs = {r["source"]["regulation"] for r in P["requirements"]}
pages = {(r["source"]["regulation"], r["source"]["page"]) for r in P["requirements"]}
written = {(r["source"]["regulation"], r["source"].get("paragraph"), r["source"]["page"]) for r in W}
cand = [c for c in candidates(regs, "shall+implicit", ("Table", "Figure", "Appendix"))
        if (c.regulation, c.page) in pages and (c.regulation, c.paragraph, c.page) not in written
        and c.page >= start.get(c.regulation, 0)]
pairs = write(spec, cand, prompt="faithful")
n0 = len(P["requirements"])
added = [{"id": f"S-{i:04d}", "text": t[:2000], "source": c.cite()} for i, (c, t) in enumerate(pairs, 1)]
json.dump({**P, "requirements": P["requirements"] + added}, open(outf, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"{case}: {len(cand)} clauses -> +{len(added)} requirements ({n0} -> {n0 + len(added)})")
