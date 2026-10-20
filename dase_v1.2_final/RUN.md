# DASE v1.2 — How to Run

## Quickstart (surrogate-free, runs in seconds)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run the full DASE experiment (12 seeds × 25 generations)
cd dase_final
python3 agent/coverage_closure.py

# 3. Run CMA-ES self-tuning (evolves the fitness weights)
python3 agent/self_tune.py --seed 42 --cma-fevals 100 --meta-seeds 6

# 4. Table 1 reproduction only (locked weights, no CMA-ES)
python3 agent/self_tune.py --seed 42 --seeds 12 --cma-fevals 0
```

## Real-sim mode (requires riscv-gcc + iverilog + cocotb)

```bash
# Install system toolchain (Ubuntu/Debian)
sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf \
                 iverilog make coreutils
pip install cocotb

# Run with real simulation (each eval ~30 seconds)
python3 agent/coverage_closure.py
```

## Expected Output

```
========== FINAL STATISTICS ==========
DASE Mean:   0.803
Random Mean: 0.765
DASE CI:     (0.803, 0.803)
Random CI:   (0.749, 0.780)
Cohen's d:   1.963
t-stat:      4.808
p-value:     0.000546
Statistically significant
```

## Files

```
dase_final/
├── config.yaml              All tunable knobs
├── requirements.txt         Python dependencies
├── RUN.md                   This file
├── agent/
│   ├── coverage_closure.py   DASE inner loop (GA: roulette + crossover)
│   └── self_tune.py          CMA-ES meta-optimizer
├── test_results/
│   ├── multi_seed_results.json   Aggregated results (3 outer seeds)
│   └── tuning_results.json       Single-seed CMA-ES results
└── docs/
    ├── DASE_Speaker_Script_All_Slides.docx
    └── DASE_Complete_Project_Documentation.docx
```

## Configuration

All knobs are in `config.yaml`. Key parameters:
- `inner.generations`: 25 (DASE generations per seed)
- `inner.population`: 8 (population size)
- `inner.seeds`: 12 (seeds for Table 1)
- `inner.mutation_rate`: 0.3 (pm)
- `inner.crossover_rate`: 0.7 (pc)
- `weights.*`: [0.40, 0.25, 0.15, 0.10, 0.10] (locked defaults)
- `ceilings.*`: [80, 15, 8] (normalization ceilings)
- `cma_es.max_fevals`: 100 (CMA-ES evaluation budget)

## Reproducibility

Same seed = same output. Override with `--seed <int>`.
