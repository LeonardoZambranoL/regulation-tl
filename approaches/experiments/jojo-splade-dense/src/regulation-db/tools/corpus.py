"""Offline search, export and auditable curation of the source-only corpus."""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent/'corpus/regulations.sqlite'


def connect(path):
    con = sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True)
    con.row_factory = sqlite3.Row
    return con


def rows(con,sql,args=()):
    return [dict(r) for r in con.execute(sql,args)]


def candidates(con,regs,role='base'):
    sql='''SELECT o.*,c.paragraph,c.kind AS block_kind,c.page_start,c.page_end,
    d.regulation,d.version,d.role,d.pdf_path FROM candidates o JOIN clauses c USING(clause_id)
    JOIN documents d USING(document_id)'''
    conditions=[];params=[]
    if regs:
        conditions.append('d.regulation IN ('+','.join('?' for _ in regs)+')');params.extend(regs)
    if role!='all': conditions.append('d.role=?');params.append(role)
    if conditions:sql+=' WHERE '+' AND '.join(conditions)
    return rows(con,sql+' ORDER BY d.regulation,c.page_start,c.clause_id,o.candidate_id',params)


def audit(con,submission,ledger,scope):
    problems=[]
    reqs=submission['requirements']
    ids={r['id'] for r in reqs}
    if len(ids)!=len(reqs): problems.append('Duplicate requirement IDs.')
    docs={(d['regulation'],d['version']):d for d in rows(con,"SELECT * FROM documents WHERE role='base'")}
    for r in reqs:
        s=r['source']; doc=docs.get((s['regulation'],s['version']))
        if not doc: problems.append(f"{r['id']}: unknown regulation/base version")
        elif not isinstance(s['page'],int) or not 1<=s['page']<=doc['page_count']:
            problems.append(f"{r['id']}: page outside source PDF")
    all_regs={r['regulation'] for r in rows(con,'SELECT regulation FROM documents')}
    scoped={r['regulation']:r for r in scope}
    if len(scoped)!=len(scope): problems.append('Duplicate regulation scope records.')
    if set(scoped)!=all_regs: problems.append('Scope matrix must address every supplied regulation exactly once.')
    for r in scope:
        if r.get('decision') not in {'primary','conditional','excluded'} or not r.get('reason','').strip():
            problems.append(f"Invalid scope decision: {r.get('regulation')}")
    selected={r['regulation'] for r in scope if r['decision'] in {'primary','conditional'}}
    expected={r['candidate_id']:r for r in candidates(con,sorted(selected))} if selected else {}
    decisions={r['candidate_id']:r for r in ledger}
    if len(decisions)!=len(ledger): problems.append('Duplicate candidate decisions.')
    missing=sorted(set(expected)-set(decisions))
    unknown=sorted(set(decisions)-set(expected))
    if missing: problems.append(f'{len(missing)} candidates in selected regulations are unreviewed.')
    if unknown: problems.append(f'{len(unknown)} coverage records are outside selected regulations.')
    represented=set()
    counts={k:0 for k in ['included','excluded','unresolved']}
    for cid,r in decisions.items():
        dec=r.get('decision')
        if dec not in counts: problems.append(f'{cid}: invalid decision'); continue
        counts[dec]+=1
        if not r.get('reason','').strip(): problems.append(f'{cid}: decision needs a reason')
        links=r.get('requirement_ids',[])
        if not isinstance(links,list): problems.append(f'{cid}: requirement_ids must be a list'); continue
        if dec=='included' and not links: problems.append(f'{cid}: included candidate has no requirement')
        if dec=='excluded' and links: problems.append(f'{cid}: excluded candidate has requirement links')
        if set(links)-ids: problems.append(f'{cid}: references unknown requirement IDs')
        if dec=='included': represented.update(links)
    unsupported=sorted(ids-represented)
    if unsupported: problems.append(f'{len(unsupported)} requirements have no included source candidate.')
    if counts['unresolved']: problems.append(f"{counts['unresolved']} candidates remain unresolved.")
    return {'passed':not problems,'problems':problems,'candidate_decisions':counts,
        'selected_regulations':sorted(selected),'missing_candidate_ids':missing,
        'requirements_without_candidate':unsupported,
        'limitation':'Checks structural traceability and decision completeness, not semantic correctness. Exclusion reasons and inferred paragraph labels require substantive review.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=DEFAULT_DB)
    p.add_argument('--role',choices=['base','latest','all'],default='base',help='Source selection; main challenge uses base. Audit always checks base.')
    sp=p.add_subparsers(dest='command',required=True)
    sp.add_parser('catalog')
    search=sp.add_parser('search');search.add_argument('query');search.add_argument('--reg');search.add_argument('--limit',type=int,default=20)
    page=sp.add_parser('page');page.add_argument('--reg',required=True);page.add_argument('--page',type=int,required=True)
    export=sp.add_parser('export');export.add_argument('--reg',action='append',required=True);export.add_argument('--out',type=Path,required=True)
    check=sp.add_parser('audit');check.add_argument('--submission',type=Path,required=True);check.add_argument('--coverage',type=Path,required=True);check.add_argument('--scope',type=Path,required=True);check.add_argument('--out',type=Path,required=True);check.add_argument('--curated-db',type=Path)
    a=p.parse_args();con=connect(a.db)
    if a.command=='catalog':
        print(json.dumps(rows(con,'SELECT d.*, (SELECT count(*) FROM clauses c WHERE c.document_id=d.document_id) AS source_blocks FROM documents d'+(' WHERE role=?' if a.role!='all' else '')+' ORDER BY regulation',[] if a.role=='all' else [a.role]),indent=2))
    elif a.command=='search':
        sql='SELECT s.clause_id,s.regulation,s.paragraph,s.text,d.version,d.role FROM clause_search s JOIN clauses c USING(clause_id) JOIN documents d USING(document_id) WHERE clause_search MATCH ?';params=[a.query]
        if a.reg: sql+=' AND d.regulation=?';params.append(a.reg)
        if a.role!='all':sql+=' AND d.role=?';params.append(a.role)
        sql+=' ORDER BY rank LIMIT ?';params.append(a.limit)
        print(json.dumps(rows(con,sql,params),indent=2))
    elif a.command=='page':
        print(json.dumps(rows(con,'SELECT d.regulation,d.version,d.role,p.page,p.text FROM pages p JOIN documents d USING(document_id) WHERE regulation=? AND page=?'+(' AND role=?' if a.role!='all' else ''),[a.reg,a.page]+([] if a.role=='all' else [a.role])),indent=2))
    elif a.command=='export':
        a.out.mkdir(parents=True,exist_ok=True)
        records=candidates(con,a.reg,a.role)
        (a.out/'candidates.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
        clauses=rows(con,'SELECT c.*,d.regulation,d.version,d.role FROM clauses c JOIN documents d USING(document_id) WHERE regulation IN ('+','.join('?' for _ in a.reg)+')'+(' AND role=?' if a.role!='all' else '')+' ORDER BY regulation,page_start,clause_id',a.reg+([] if a.role=='all' else [a.role]))
        (a.out/'clauses.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in clauses))
        for reg in a.reg:
            data=rows(con,'SELECT page,text,version,role FROM pages p JOIN documents d USING(document_id) WHERE regulation=?'+(' AND role=?' if a.role!='all' else '')+' ORDER BY version,page',[reg]+([] if a.role=='all' else [a.role]))
            (a.out/(reg.replace(' ','_')+'.txt')).write_text('\n\n'.join(f"===== {reg} VERSION {r['version']} ROLE {r['role']} PDF PAGE {r['page']} =====\n{r['text']}" for r in data))
        print(json.dumps({'candidates':len(records),'blocks':len(clauses),'output':str(a.out)},indent=2))
    elif a.command=='audit':
        submission=json.loads(a.submission.read_text());scope=json.loads(a.scope.read_text())
        ledger=[json.loads(line) for line in a.coverage.read_text().splitlines() if line.strip()]
        result=audit(con,submission,ledger,scope)
        a.out.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
        if a.curated_db:
            if not result['passed']: raise SystemExit('Resolve audit failures before writing curated database.')
            if a.curated_db.resolve()==a.db.resolve(): raise SystemExit('Cannot overwrite source corpus.')
            if a.curated_db.exists(): raise SystemExit('Refusing to overwrite curated database.')
            target=sqlite3.connect(a.curated_db);con.backup(target)
            for r in submission['requirements']:
                s=r['source'];provenance=[l['candidate_id'] for l in ledger if r['id'] in l.get('requirement_ids',[]) and l['decision']=='included']
                context=next((x['reason'] for x in scope if x['regulation']==s['regulation']),'')
                target.execute('INSERT INTO curated_obligations VALUES (?,?,?,?,?,?,?,?)',(r['id'],r['text'],s['regulation'],s['version'],s['page'],s.get('paragraph',''),context,json.dumps(provenance)))
            target.executemany('INSERT INTO coverage VALUES (?,?,?,?)',[(r['candidate_id'],r['decision'],r['reason'],json.dumps(r.get('requirement_ids',[]))) for r in ledger])
            target.commit();target.close()
        if not result['passed']: raise SystemExit(1)
    con.close()


if __name__=='__main__':
    main()
