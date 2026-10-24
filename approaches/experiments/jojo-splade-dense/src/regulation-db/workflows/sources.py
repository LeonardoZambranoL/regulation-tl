"""Read-only base-version source access, page packets and bounded reference expansion."""
import hashlib
import re
import sqlite3
from collections import defaultdict, deque
from pathlib import Path

import pypdfium2

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'regulation-db/corpus/regulations.sqlite'


class Sources:
    def __init__(self, db=DB):
        self.path = Path(db)
        self.con = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        self.con.row_factory = sqlite3.Row
        self.docs = {d['document_id']: dict(d) for d in self.con.execute("SELECT * FROM documents WHERE role='base'")}
        self.by_reg = defaultdict(list)
        for d in self.docs.values():
            self.by_reg[d['regulation']].append(d)
        self.pages = {(r['document_id'], r['page']): dict(r) for r in self.con.execute(
            "SELECT p.* FROM pages p JOIN documents d USING(document_id) WHERE d.role='base'")}
        self.clauses = {r['clause_id']: dict(r) for r in self.con.execute(
            "SELECT c.* FROM clauses c JOIN documents d USING(document_id) WHERE d.role='base'")}
        self.by_document = defaultdict(list)
        for clause in self.clauses.values():
            self.by_document[clause['document_id']].append(clause)
        self.candidates = {}
        self.by_page = defaultdict(list)
        for r in self.con.execute('SELECT * FROM candidates'):
            if r['clause_id'] not in self.clauses:
                continue
            item = dict(r)
            c = self.clauses[item['clause_id']]
            item.update(document_id=c['document_id'], page=c['page_start'], paragraph=c['paragraph'])
            self.candidates[item['candidate_id']] = item
            self.by_page[(c['document_id'], c['page_start'])].append(item)
        self.refs = defaultdict(list)
        for r in self.con.execute('SELECT * FROM source_references'):
            if r['clause_id'] in self.clauses:
                self.refs[r['clause_id']].append(dict(r))
        self.fingerprint = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def catalog_packet(self, regulations):
        result = []
        for reg in regulations:
            docs = self.by_reg[reg]
            result.append({'regulation': reg, 'documents': [
                {'version': d['version'], 'title': d['title'], 'page_count': d['page_count'],
                 'opening_pages': [self.pages[(d['document_id'], p)]
                                   for p in range(1, min(3, d['page_count']) + 1)]} for d in docs]})
        return result

    def packet(self, document_id, first, count=3):
        doc = self.docs[document_id]
        main = list(range(first, min(first + count, doc['page_count'] + 1)))
        context = [p for p in [first - 1, main[-1] + 1] if 1 <= p <= doc['page_count']]
        section_context = self.ancestors(document_id, main + context)
        # Carry the opening page of every governing section, including its general conditions.
        roots = [r for r in section_context if not any(
            r['paragraph'].startswith(a['paragraph'] + '.') or r['paragraph'].startswith(a['paragraph'] + ' ')
            for a in section_context if a is not r)]
        context = sorted(set(context + [r['page'] for r in roots]) - set(main))
        candidates = [c for p in main for c in self.by_page[(document_id, p)]]
        cids = {c['clause_id'] for c in candidates}
        refs = [r for cid in sorted(cids) for r in self.refs[cid]]
        return {'id': f'{document_id}:P{first:04}', 'regulation': doc['regulation'], 'version': doc['version'],
                'document_id': document_id, 'main_pages': main,
                'section_context': section_context,
                'pages': [{**self.pages[(document_id, p)], 'context_only': p not in main} for p in sorted(main + context)],
                'owned_candidates': [{k: c[k] for k in ['candidate_id', 'clause_id', 'page', 'paragraph', 'source_text']}
                                     for c in candidates],
                'references': refs}

    def ancestors(self, document_id, pages):
        clauses = self.by_document[document_id]
        children = [c for c in clauses if c['page_start'] in pages]
        found = {}
        for child in children:
            label = (child['paragraph'] or '').rstrip('.')
            nearest = {}
            for parent in clauses:
                name = (parent['paragraph'] or '').rstrip('.')
                if (name and (parent['page_start'], parent['clause_id']) < (child['page_start'], child['clause_id']) and
                        (label.startswith(name + '.') or label.startswith(name + ' '))):
                    if name not in nearest or (parent['page_start'], parent['clause_id']) > (nearest[name]['page_start'], nearest[name]['clause_id']):
                        nearest[name] = parent
            for name, parent in nearest.items():
                found[parent['clause_id']] = {'paragraph': name, 'page': parent['page_start'], 'text': parent['text']}
        return sorted(found.values(), key=lambda r: (r['page'], r['paragraph']))

    def packets(self, regulations, pages=None, count=3):
        output = []
        for did, doc in sorted(self.docs.items()):
            if doc['regulation'] not in regulations:
                continue
            for first in range(1, doc['page_count'] + 1, count):
                if pages is None or any((did, p) in pages for p in range(first, min(first + count, doc['page_count'] + 1))):
                    output.append(self.packet(did, first, count))
        return output

    def expand(self, seed_ids, allowed_regs, depth=2):
        queue = deque((cid, 0) for cid in seed_ids)
        seen, pages, unresolved = set(), [], []
        while queue:
            cid, level = queue.popleft()
            if cid in seen or cid not in self.clauses:
                continue
            seen.add(cid)
            clause = self.clauses[cid]
            did = clause['document_id']
            if self.docs[did]['regulation'] not in allowed_regs:
                continue
            pages.extend((did, p) for p in range(clause['page_start'], clause['page_end'] + 1))
            for ref in self.refs[cid]:
                if not ref['target_clause_id']:
                    unresolved.append(ref)
                elif level < depth:
                    queue.append((ref['target_clause_id'], level + 1))
        return list(dict.fromkeys(pages)), unresolved

    def render(self, did, page, root):
        destination = Path(root) / 'page-images' / f'{did}-p{page}.jpg'
        if destination.exists():
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf = pypdfium2.PdfDocument(self.docs[did]['pdf_path'])
        try:
            p = pdf[page - 1]
            bitmap = p.render(scale=1.5)
            image = bitmap.to_pil().convert('RGB')
            image.save(destination, quality=88)
            image.close()
            bitmap.close()
            p.close()
        finally:
            pdf.close()
        return destination

    def images(self, packet, root):
        # The original page matters for tables and diagrams even when extracted text looks nonempty.
        return [(f"SOURCE IMAGE: {packet['regulation']} version {packet['version']} PDF page {p}",
                 self.render(packet['document_id'], p, root)) for p in packet['main_pages']]
