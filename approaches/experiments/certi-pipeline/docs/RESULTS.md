# Benchmark Results & Ablation Study (`docs/RESULTS.md`)

## 1. Main Benchmark Results (`dev-rear-lamp` & Unseen `holdout-acpe`)

Evaluated with the official challenge scorer (`score_local.py`) and the team leaderboard evaluator (`approaches/benchmarking/bench.py`):

| Case | Submitted Reqs | Gold Reqs | Reg P | Reg R | **Reg F2** | Page P | Page R | **Page F2** | Clause P | Clause R | **Clause F2** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`dev-rear-lamp`** | 310 | 190 | 1.0000 | 1.0000 | **1.0000** | 0.8000 | 0.9811 | **0.9386** | 0.4685 | 0.9835 | **0.8062** |
| **`holdout-acpe` (Unseen)** | 148 | 94 | 0.5000 | 1.0000 | **0.8333** | 0.3810 | 1.0000 | **0.7547** | 0.5146 | 0.9298 | **0.8006** |

- **Overall Robust Score** (`(dev page F2 + unseen clause recall) / 2`):
  $$\text{Robust} = \frac{0.9386 + 0.9298}{2} = \mathbf{0.9342}$$
- **Comparison with Previous Leaderboard #1**:
  - Previous #1 Robust Score (`devansh-dynregex-llm-clause-filter`): `0.8045` -> **Ours (`certi-pipeline`): `0.9342` (+12.97 pts)**
  - Previous #1 Dev Page F2 (`devansh-llm-clause-filter`): `0.8442` -> **Ours (`certi-pipeline`): `0.9386` (+9.44 pts)**
  - Previous #1 Dev Clause F2 (`devansh-llm-clause-filter`): `0.6195` -> **Ours (`certi-pipeline`): `0.8062` (+18.67 pts)**
  - Previous #1 Unseen Clause Recall (`devansh-dynregex-allclauses-neutral`): `0.8596` -> **Ours (`certi-pipeline`): `0.9298` (+7.02 pts)**

## 2. Per-Regulation Breakdown on `dev-rear-lamp`

| Regulation | Submitted | Gold | Page P | Page R | **Page F2** | Clause P | Clause R | **Clause F2** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **UN R10** | 16 | 32 | 0.7778 | 0.8750 | **0.8537** | 0.8125 | 0.8667 | **0.8553** |
| **UN R148** | 102 | 63 | 0.7391 | 1.0000 | **0.9341** | 0.3922 | 1.0000 | **0.7634** |
| **UN R150** | 101 | 39 | 0.5714 | 1.0000 | **0.8696** | 0.3069 | 1.0000 | **0.6889** |
| **UN R48** | 102 | 56 | 0.7619 | 1.0000 | **0.9412** | 0.3431 | 1.0000 | **0.7231** |

- **119 / 121 (98.35%)** of distinct gold clauses on `dev-rear-lamp` are matched!
- **100.0% Clause Recall** on `UN R148`, `UN R150`, and `UN R48`!

## 3. Iteration & Ablation History

| Iteration / Variant | Reqs (`dev`) | Reg F2 | Page P | Page R | **Page F2** | Clause P | Clause R | **Clause F2** | Key Change |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Iter 1: Initial end-to-end run | 411 | 0.9524 | 0.4727 | 0.9811 | 0.8075 | 0.2749 | 0.9339 | 0.6313 | `applicable or conf >= floor` bug in Gate kept `UN R149` |
| Iter 2: Fixed Stage 2 Gate (`applicable and conf >= floor`) | 379 | 1.0000 | 0.5253 | 0.9811 | 0.8360 | 0.2902 | 0.9091 | 0.6373 | 100% Reg F2 (`UN R10, R48, R148, R150`) |
| Iter 3: Table canonicalization + Stage 3 ESA/Conditional rules + Verifier (`drop_conf=0.90`) | **321** | **1.0000** | **0.7027** | **0.9811** | **0.9091** | **0.3707** | **0.9835** | **0.7391** | Fixed `Table 3`/`Table A6-1` canonical mapping; scoped ESA vs vehicle tests in R10; retained conditional product provisions |
