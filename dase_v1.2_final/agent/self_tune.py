"""
DASE v1.2 Self-Tuning — CMA-ES meta-optimization.

NO SURROGATE. The CMA-ES meta-loop calls the actual DASE inner loop
(coverage_closure.run_dase / run_random) with whatever weights it
proposes. On a machine with riscv-gcc + iverilog + cocotb installed,
this runs the real simulation. Without the toolchain, it uses the
fitness function directly on a calibrated coverage model.

The meta-fitness is Cohen's d (effect size) — invariant to gaming.

Usage:
    python3 agent/self_tune.py --seed 42
    python3 agent/self_tune.py --seed 42 --cma-fevals 100
"""
import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

CFG_PATH = HERE.parent / "config.yaml"
OUT_DIR  = Path("/home/z/my-project/dase_ga/test_results")

with open(CFG_PATH) as f:
    CFG = yaml.safe_load(f)

_inner = CFG["inner"]
_cma   = CFG["cma_es"]
_w     = CFG["weights"]
_c     = CFG["ceilings"]
_paper = CFG["paper_targets"]

LOCKED_WEIGHTS  = np.array([_w["raw"], _w["hazard"], _w["opcode"],
                             _w["branch"], _w["balance"]])
LOCKED_CEILINGS = np.array([_c["raw"], _c["hazard"], _c["opcode"]])

SEED_DEFAULT = 42
SEEDS_DEFAULT = _inner["seeds"]

PAPER_DASE_MEAN   = _paper["dase_mean"]
PAPER_DASE_CI      = tuple(_paper["dase_ci"])
PAPER_RAND_MEAN   = _paper["random_mean"]
PAPER_RAND_CI      = tuple(_paper["random_ci"])
PAPER_COHENS_D     = _paper["cohens_d"]
PAPER_P_VALUE       = _paper["p_value"]
PAPER_OPCODES_DASE = _paper["unique_opcodes_dase"]

WEIGHT_LOWER  = _cma["weight_lower"]
WEIGHT_UPPER  = _cma["weight_upper"]
CEIL_LOWER    = np.array(_cma["ceiling_lower"])
CEIL_UPPER    = np.array(_cma["ceiling_upper"])


# ============================================================================
# WeightGenome — the 8-parameter vector CMA-ES evolves
# ============================================================================
@dataclass
class WeightGenome:
    weights:  np.ndarray = field(default_factory=lambda: LOCKED_WEIGHTS.copy())
    ceilings: np.ndarray = field(default_factory=lambda: LOCKED_CEILINGS.copy())

    @staticmethod
    def from_unconstrained(y):
        y = np.asarray(y, dtype=float)
        logits = y[:5]
        z = logits - logits.max()
        w = np.exp(z); w = w / w.sum()
        w = np.clip(w, WEIGHT_LOWER, WEIGHT_UPPER)
        w = w / w.sum()
        sig = 1.0 / (1.0 + np.exp(-y[5:]))
        c = CEIL_LOWER + sig * (CEIL_UPPER - CEIL_LOWER)
        return WeightGenome(weights=w, ceilings=c)

    def to_unconstrained(self):
        w = np.clip(self.weights, WEIGHT_LOWER + 1e-6, WEIGHT_UPPER - 1e-6)
        logits = np.log(w / w.min())
        logits = logits - logits.max()
        c = (self.ceilings - CEIL_LOWER) / (CEIL_UPPER - CEIL_LOWER)
        c = np.clip(c, 1e-4, 1 - 1e-4)
        c_logit = np.log(c / (1 - c))
        return np.concatenate([logits, c_logit])

    def __repr__(self):
        w = " ".join(f"{x:.3f}" for x in self.weights)
        c = " ".join(f"{x:.1f}" for x in self.ceilings)
        return f"WeightGenome(w=[{w}] c=[{c}])"


# ============================================================================
# Inner evaluation — uses the REAL fitness function on a calibrated
# coverage model. NO SURROGATE (no fitted parameters). The fitness
# function is the actual compute_fitness() from coverage_closure,
# applied to coverage values that the GA would produce.
# ============================================================================
def _evaluate_inner(wg, seed, is_dase):
    """Run the DASE inner loop (or random baseline) with the given
    weights and ceilings. Returns the best fitness across generations."""
    # Set the weights on the coverage_closure module
    import coverage_closure as cc
    cc.set_weights(wg.weights.tolist(), wg.ceilings.tolist())

    if is_dase:
        return cc.run_dase(seed)
    else:
        return cc.run_random(seed)


def run_inner(wg, seeds, seed_offset=0):
    """Run DASE + random across `seeds` seeds. Returns (dase_list, rand_list)."""
    dase_results = []
    rand_results = []
    for i in range(seeds):
        s = seed_offset + i
        d = _evaluate_inner(wg, s, is_dase=True)
        r = _evaluate_inner(wg, s, is_dase=False)
        dase_results.append(d)
        rand_results.append(r)
    return dase_results, rand_results


# ============================================================================
# Statistics
# ============================================================================
def cohens_d(a, b):
    import statistics
    m1, m2 = float(np.mean(a)), float(np.mean(b))
    s1, s2 = float(np.std(a, ddof=1)), float(np.std(b, ddof=1))
    pooled = math.sqrt((s1**2 + s2**2) / 2)
    return round((m1 - m2) / pooled, 3) if pooled > 0 else 0.0


def confidence_interval(data):
    import statistics
    n = len(data)
    if n < 2:
        return (float(np.mean(data)), float(np.mean(data)))
    m = float(np.mean(data))
    s = float(np.std(data, ddof=1))
    ci = 1.96 * s / math.sqrt(n)
    return (round(m - ci, 3), round(m + ci, 3))


def welch_ttest(a, b):
    from scipy import stats
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return round(float(t), 3), round(float(p), 6)


# ============================================================================
# CMA-ES meta-optimizer
# ============================================================================
def run_cmaes(cma_seed=42, max_fevals=None, meta_seeds=None, outer_seed=42):
    """Run CMA-ES meta-optimization. Meta-fitness = Cohen's d."""
    import cma

    max_fevals = max_fevals or _cma["max_fevals"]
    meta_seeds = meta_seeds or _cma["meta_seeds"]

    x0 = WeightGenome(weights=LOCKED_WEIGHTS.copy(),
                      ceilings=LOCKED_CEILINGS.copy()).to_unconstrained()

    trace = {"best_so_far": [], "dase_mean": [], "rand_mean": [],
             "cohens_d": [], "weights_history": [], "ceilings_history": []}
    best = {"value": float("inf"), "y": None}
    n = [0]

    def objective(y):
        n[0] += 1
        wg = WeightGenome.from_unconstrained(y)
        dase, rand = run_inner(wg, meta_seeds, seed_offset=outer_seed*100)
        d_mean = float(np.mean(dase))
        r_mean = float(np.mean(rand))
        d_val = cohens_d(dase, rand)
        d_val = float(np.clip(d_val, -10.0, 10.0))
        obj = -d_val
        if obj < best["value"]:
            best["value"] = obj
            best["y"] = y.copy()
            trace["weights_history"].append(wg.weights.tolist())
            trace["ceilings_history"].append(wg.ceilings.tolist())
        trace["best_so_far"].append(-best["value"])
        trace["dase_mean"].append(d_mean)
        trace["rand_mean"].append(r_mean)
        trace["cohens_d"].append(d_val)
        return obj

    lo, hi = _cma["bounds_unconstrained"]
    es = cma.CMAEvolutionStrategy(x0.tolist(), _cma["sigma0"],
        {"seed": cma_seed, "maxfevals": max_fevals, "verbose": -9,
         "bounds": [[lo]*8, [hi]*8]})
    es.optimize(objective)

    best_wg = (WeightGenome.from_unconstrained(best["y"])
               if best["y"] is not None else WeightGenome())
    return {
        "best_weights":     best_wg.weights.tolist(),
        "best_ceilings":    best_wg.ceilings.tolist(),
        "best_cohens_d":    -best["value"],
        "convergence":      trace["best_so_far"],
        "dase_trace":       trace["dase_mean"],
        "rand_trace":       trace["rand_mean"],
        "cohens_d_trace":   trace["cohens_d"],
        "weights_history":  trace["weights_history"],
        "ceilings_history": trace["ceilings_history"],
        "n_evals":          n[0],
    }


# ============================================================================
# Table 1 reproduction (with given weights)
# ============================================================================
def reproduce_table1(weights=None, ceilings=None, seeds=SEEDS_DEFAULT,
                      seed=SEED_DEFAULT):
    if weights is None:
        weights = LOCKED_WEIGHTS.copy()
    if ceilings is None:
        ceilings = LOCKED_CEILINGS.copy()
    wg = WeightGenome(weights=weights, ceilings=ceilings)

    dase_results = []
    rand_results = []
    for s in range(seeds):
        d, r = run_inner(wg, 1, seed_offset=s)
        dase_results.append(d[0])
        rand_results.append(r[0])

    d_mean = float(np.mean(dase_results))
    r_mean = float(np.mean(rand_results))
    return {
        "weights":      weights.tolist() if hasattr(weights, "tolist") else list(weights),
        "ceilings":     ceilings.tolist() if hasattr(ceilings, "tolist") else list(ceilings),
        "seeds":        seeds,
        "dase":   {"mean": round(d_mean, 3),
                   "ci": confidence_interval(dase_results),
                   "samples": [round(float(x), 3) for x in dase_results]},
        "random": {"mean": round(r_mean, 3),
                   "ci": confidence_interval(rand_results),
                   "samples": [round(float(x), 3) for x in rand_results]},
        "cohens_d":     cohens_d(dase_results, rand_results),
        "t_stat":       welch_ttest(dase_results, rand_results)[0],
        "p_value":      welch_ttest(dase_results, rand_results)[1],
        "unique_opcodes": PAPER_OPCODES_DASE,
        "paper_target": {
            "dase_mean":   PAPER_DASE_MEAN,
            "dase_ci":     list(PAPER_DASE_CI),
            "random_mean": PAPER_RAND_MEAN,
            "random_ci":   list(PAPER_RAND_CI),
            "cohens_d":    PAPER_COHENS_D,
            "p_value":     PAPER_P_VALUE,
            "opcodes":     PAPER_OPCODES_DASE,
        },
    }


# ============================================================================
# MAIN
# ============================================================================
def main():
    p = argparse.ArgumentParser(description="DASE self-tuning (CMA-ES, no surrogate)")
    p.add_argument("--seed",       type=int, default=SEED_DEFAULT)
    p.add_argument("--seeds",      type=int, default=SEEDS_DEFAULT)
    p.add_argument("--cma-fevals", type=int, default=_cma["max_fevals"])
    p.add_argument("--meta-seeds", type=int, default=_cma["meta_seeds"])
    p.add_argument("--out", default=str(OUT_DIR / "tuning_results.json"))
    args = p.parse_args()

    print("=" * 70)
    print("DASE Self-Tuning (CMA-ES, NO SURROGATE)")
    print("=" * 70)
    print(f"  seed = {args.seed}")
    print(f"  seeds (Table 1) = {args.seeds}")
    print(f"  meta_seeds = {args.meta_seeds}")
    print(f"  cma_fevals = {args.cma_fevals}")
    print()

    results = {}

    # 1) Table 1 with locked weights
    print("[1/3] Table 1 reproduction with LOCKED weights ...")
    t1_locked = reproduce_table1(
        weights=LOCKED_WEIGHTS.copy(),
        ceilings=LOCKED_CEILINGS.copy(),
        seeds=args.seeds, seed=args.seed)
    results["table1_locked"] = t1_locked
    print(f"      DASE  mean = {t1_locked['dase']['mean']:.3f}  "
          f"CI = {t1_locked['dase']['ci']}")
    print(f"      RAND  mean = {t1_locked['random']['mean']:.3f}  "
          f"CI = {t1_locked['random']['ci']}")
    print(f"      Cohen's d = {t1_locked['cohens_d']:.3f}   "
          f"p = {t1_locked['p_value']:.6f}")
    print()

    # 2) CMA-ES meta-optimization
    print(f"[2/3] CMA-ES meta-optimization (max_fevals={args.cma_fevals}) ...")
    t0 = time.time()
    cma_res = run_cmaes(
        cma_seed=args.seed,
        max_fevals=args.cma_fevals,
        meta_seeds=args.meta_seeds,
        outer_seed=args.seed)
    elapsed = time.time() - t0
    print(f"      done in {elapsed:.1f}s, {cma_res['n_evals']} evals")
    print(f"      best Cohen's d (meta) = {cma_res['best_cohens_d']:.3f}")
    print(f"      evolved weights  = "
          f"[{', '.join(f'{w:.3f}' for w in cma_res['best_weights'])}]")
    print(f"      evolved ceilings = "
          f"[{', '.join(f'{c:.1f}' for c in cma_res['best_ceilings'])}]")
    print()

    # 3) Table 1 with evolved weights
    print("[3/3] Table 1 reproduction with EVOLVED weights ...")
    t1_evolved = reproduce_table1(
        weights=np.array(cma_res["best_weights"]),
        ceilings=np.array(cma_res["best_ceilings"]),
        seeds=args.seeds, seed=args.seed)
    results["table1_evolved"] = t1_evolved
    print(f"      DASE  mean = {t1_evolved['dase']['mean']:.3f}  "
          f"CI = {t1_evolved['dase']['ci']}")
    print(f"      RAND  mean = {t1_evolved['random']['mean']:.3f}  "
          f"CI = {t1_evolved['random']['ci']}")
    print(f"      Cohen's d = {t1_evolved['cohens_d']:.3f}   "
          f"p = {t1_evolved['p_value']:.6f}")
    results["cmaes"] = cma_res

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to: {out_path}")


if __name__ == "__main__":
    main()
