# Challenge scoring tool

`score_local.py` is an unmodified copy of
`industrial-ai-hackathon/tools/score_local.py`, copied on 2026-10-24 from the
local challenge checkout. The accompanying LICENSE is copied from that repository
and covers this tool (MIT, Copyright 2026 Certivity).

`../bench.py` calls its `score(submission, expected)` function and adds F2 using
the returned precision and recall. All official fields, including F1 and counts,
are preserved. The scorer's SHA-256 is recorded with each result and included in
the evaluator identifier so changed scorer versions have separate rankings.

`validate.py` and both files in `schemas/` are also unmodified copies from the
same checkout. The wrapper calls `read_submission` and `validate` for both inputs
before scoring. These enforce the official file-size, schema, and duplicate-ID
rules. Passing `--index` enables regulation/version membership checks as well.
The validator requires jsonschema; install `../requirements.txt`.

To update, copy the upstream tools and schemas here unchanged, retaining LICENSE.
