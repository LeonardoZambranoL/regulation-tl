"""Build a source-only searchable regulation corpus; never read expected answers.

Automatic clause labels/candidates are navigation aids, not verified legal records.
The untouched PDF and complete page text remain authoritative.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ANNEX = re.compile(r"^Annex\s+(\d+)\s+([A-Z][^\n]{2,})$")
PART = re.compile(r"^Part\s+(\d+)\s*[-–:]\s*(.+)$")
PARAGRAPH = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+(\S.*)$")
TABLE = re.compile(r"^(Table\s+[A-Z]?\d+(?:[-–.]\d+|[-–][A-Z0-9]+)*[a-z]?)(?:\s|:)", re.I)
MODAL = re.compile(r"\b(shall|must|required|requirements?|permitted|shall not|may not|at least|not exceed|not less than|not more than)\b", re.I)
LIMIT = re.compile(r"(?:[<>≤≥±+−-]\s*)?\d+(?:[.,]\d+)?\s*(?:%|per cent|percent|mm|cm2|cm|m2|m|cd|mcd|lux|lx|V|MHz|kHz|Hz|dB|°C|°|degrees?|hours?|minutes?|seconds?|ms|µs)\b", re.I)
REF = re.compile(r"(?:UN Regulation(?:s)?(?: No(?:s)?\.)?\s*\d+|Annex\s+\d+(?:\s+Part\s+\d+)?|Table\s+[A-Z]?\d+(?:[-–.]\d+|[-–][A-Z0-9]+)*[a-z]?|paragraph(?:s)?\s+\d+(?:\.\d+)*)", re.I)


def clean_page(text):
    lines = []
    for raw in text.splitlines():
        line = unicodedata.normalize("NFKC", raw).strip()
        if re.match(r"^UN .+version .+\| page \d+ of \d+", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def segments(pages):
    """Preserve page continuations and annex/part context in source blocks."""
    result, current = [], None
    annex = part = None
    def flush():
        nonlocal current
        if current and current['lines']:
            current['text'] = '\n'.join(current.pop('lines'))
            result.append(current)
        current = None
    for page, text in enumerate(pages, 1):
        for line in clean_page(text).splitlines():
            if not line:
                continue
            a, p, t, n = ANNEX.match(line), PART.match(line), TABLE.match(line), PARAGRAPH.match(line)
            if a:
                flush(); annex, part = a.group(1), None
                label, kind = f'Annex {annex}', 'heading'
            elif p and annex:
                flush(); part = p.group(1)
                label, kind = f'Annex {annex} Part {part}', 'heading'
            elif t:
                flush(); label, kind = ' '.join(filter(None, [f'Annex {annex}' if annex else None, f'Part {part}' if part else None, t.group(1)])), 'table'
            elif n and ('.' in line.split()[0] or re.match(r'^[A-Z][a-zA-Z]{2,}\b',n.group(2))) and not re.match(r'^[\d\s.,±+−/%-]+$', line):
                flush(); label, kind = ' '.join(filter(None, [f'Annex {annex}' if annex else None, f'Part {part}' if part else None, n.group(1)])), 'clause'
            else:
                label = kind = None
            if current is None:
                current = {'paragraph':label or '', 'kind':kind or 'unlabelled', 'page_start':page, 'page_end':page, 'lines':[]}
            current['lines'].append(line)
            current['page_end'] = page
    flush()
    return result


def extract(job):
    from pypdf import PdfReader
    path = Path(job['pdf_path'])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != job['sha256']:
        raise ValueError(f"Checksum mismatch: {path}")
    reader = PdfReader(path)
    pages = [p.extract_text(extraction_mode='layout') or '' for p in reader.pages]
    return job, pages, segments(pages)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--role', choices=['base','latest','all'], default='all')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    index = json.loads((args.repo/'regulations/index.json').read_text())
    jobs = []
    for item in index:
        slug = '_'.join(item['regulation'].replace('/',' ').split())
        for version in item['versions']:
            if args.role != 'all' and version['role'] != args.role:
                continue
            for f in version['files']:
                name = f['name']
                src = args.repo/'regulations/pdf'/slug/version['role']/name
                dst = args.out/'pdf'/slug/name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(src,dst)
                jobs.append({'document_id':slug+'_'+version['version_label']+'_'+Path(name).stem,
                    'regulation':item['regulation'],'title':item['title'],'version':version['version_label'],'role':version['role'],
                    'sha256':f['sha256'],'pdf_path':str(dst.resolve())})
    dbpath = args.out/'regulations.sqlite'
    if dbpath.exists():
        raise SystemExit('Refusing to overwrite existing database; choose a new output directory.')
    con = sqlite3.connect(dbpath)
    con.executescript('''
      PRAGMA foreign_keys=ON;
      CREATE TABLE documents(document_id TEXT PRIMARY KEY,regulation TEXT,version TEXT,role TEXT,title TEXT,sha256 TEXT,pdf_path TEXT,page_count INTEGER);
      CREATE TABLE pages(document_id TEXT REFERENCES documents,page INTEGER,text TEXT,PRIMARY KEY(document_id,page));
      CREATE TABLE clauses(clause_id TEXT PRIMARY KEY,document_id TEXT REFERENCES documents,paragraph TEXT,kind TEXT,page_start INTEGER,page_end INTEGER,text TEXT);
      CREATE TABLE candidates(candidate_id TEXT PRIMARY KEY,clause_id TEXT REFERENCES clauses,source_text TEXT,kind TEXT,limits_json TEXT,conditions_json TEXT,references_json TEXT,status TEXT DEFAULT 'requires_review');
      CREATE TABLE source_references(clause_id TEXT REFERENCES clauses,reference_text TEXT,target_clause_id TEXT,resolution TEXT);
      CREATE VIRTUAL TABLE clause_search USING fts5(clause_id UNINDEXED,regulation,paragraph,text);
      CREATE INDEX clause_document ON clauses(document_id,page_start);
      CREATE INDEX candidate_clause ON candidates(clause_id);
      CREATE TABLE curated_obligations(requirement_id TEXT PRIMARY KEY,text TEXT,regulation TEXT,version TEXT,page INTEGER,paragraph TEXT,applicability TEXT,provenance_ids_json TEXT);
      CREATE TABLE coverage(candidate_id TEXT PRIMARY KEY REFERENCES candidates,decision TEXT,reason TEXT,requirement_ids_json TEXT);
    ''')
    manifest = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        for job, pages, blocks in pool.map(extract,jobs):
            did = job['document_id']
            con.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)',(did,job['regulation'],job['version'],job['role'],job['title'],job['sha256'],job['pdf_path'],len(pages)))
            con.executemany('INSERT INTO pages VALUES (?,?,?)',[(did,n,t) for n,t in enumerate(pages,1)])
            outtext = args.out/'text'/f'{did}.txt'
            outtext.parent.mkdir(exist_ok=True)
            outtext.write_text('\n\n'.join(f'===== PDF PAGE {n} =====\n{t}' for n,t in enumerate(pages,1)))
            labels = {}
            for i,b in enumerate(blocks,1):
                cid = f'{did}:C{i:05}'
                labels.setdefault(b['paragraph'],[]).append(cid)
                con.execute('INSERT INTO clauses VALUES (?,?,?,?,?,?,?)',(cid,did,b['paragraph'],b['kind'],b['page_start'],b['page_end'],b['text']))
                con.execute('INSERT INTO clause_search VALUES (?,?,?,?)',(cid,job['regulation'],b['paragraph'],b['text']))
                statements = [b['text']] if b['kind']=='table' else re.split(r'(?<=[.;])\s+(?=[A-Z][a-z])', ' '.join(b['text'].split()))
                for j,s in enumerate(statements,1):
                    if not MODAL.search(s) and b['kind']!='table' and not LIMIT.search(s):
                        continue
                    refs = sorted(set(REF.findall(s)))
                    conditions = re.findall(r'\b(?:if|when|where|unless|except|provided that|in the case of)\b[^.;]{0,240}',s,re.I)
                    con.execute('INSERT INTO candidates(candidate_id,clause_id,source_text,kind,limits_json,conditions_json,references_json) VALUES (?,?,?,?,?,?,?)',
                        (f'{cid}:O{j:03}',cid,s,'table' if b['kind']=='table' else 'normative_candidate',json.dumps(LIMIT.findall(s)),json.dumps(conditions),json.dumps(refs)))
                for ref in sorted(set(REF.findall(b['text']))):
                    con.execute('INSERT INTO source_references VALUES (?,?,NULL,?)',(cid,ref,'unresolved'))
            for cid, ref in con.execute('SELECT clause_id,reference_text FROM source_references WHERE clause_id LIKE ?', (did+':%',)).fetchall():
                label = re.sub(r'^paragraphs?\s+','',ref,flags=re.I)
                # Only resolve exact, unique labels. Annex-local references remain
                # unresolved rather than silently linking to a body paragraph.
                source_label = con.execute('SELECT paragraph FROM clauses WHERE clause_id=?',(cid,)).fetchone()[0]
                context = re.match(r'^(Annex \d+(?: Part \d+)?)',source_label)
                if context and label[0:1].isdigit():
                    label = context.group(1)+' '+label
                targets = labels.get(label,[])
                if len(targets)==1:
                    con.execute('UPDATE source_references SET target_clause_id=?,resolution=? WHERE clause_id=? AND reference_text=?',(targets[0],'exact_unique_label',cid,ref))
            con.commit()
            manifest.append({**job,'page_count':len(pages),'clause_count':len(blocks)})
            print(f"{job['regulation']}: {len(pages)} pages, {len(blocks)} source blocks",flush=True)
    summary={table:con.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ['documents','pages','clauses','candidates','source_references']}
    summary['foreign_key_errors']=con.execute('PRAGMA foreign_key_check').fetchall()
    summary['integrity']=con.execute('PRAGMA integrity_check').fetchone()[0]
    con.close()
    (args.out/'manifest.json').write_text(json.dumps({'source_only':True,'extraction_note':'Machine candidates and inferred labels require source verification; tables may require PDF rendering. No reference answers or previous submissions used.','counts':summary,'documents':manifest},indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
