# DASE: Directed Adaptive Stimulus Evolution

**Coverage-Directed Evolutionary Stimulus Generation for RISC-V RTL Verification**

A lightweight, self-tuning evolutionary framework for structural coverage closure in RISC-V processor verification.

---

## Overview

DASE (Directed Adaptive Stimulus Evolution) is a closed-loop evolutionary framework that automatically generates test programs for verifying the PicoRV32 RISC-V CPU core. It uses a Genetic Algorithm (roulette-wheel selection + crossover + mutation) to evolve RISC-V assembly programs that stress the microarchitectural structures where bugs hide — forwarding logic, memory hazards, decoder paths, and branch predictors.

A CMA-ES (Covariance Matrix Adaptation Evolution Strategy) meta-layer self-tunes the fitness weights automatically — no hardcoded magic numbers.

## The Problem

- **Verification bottleneck:** >50% of design effort spent on verification
- **CRV limitations:** Constrained Random Verification struggles to reach deep corner cases (RAW chains, load-after-store hazards, complex branch interactions)
- **Heavy infrastructure:** Existing ML/RL/Fuzzing approaches need GPU, FPGA, or training data
- **RISC-V gap:** Open ISA shifts verification burden to design teams

## Key Features

- **Lightweight:** Pure software stack (Python + cocotb + Icarus Verilog + riscv-gcc). Runs on a laptop — no GPU, no FPGA
- **Self-tuning:** CMA-ES evolves the 5 fitness weights + 3 normalization ceilings. Zero hardcoded values
- **Gaming-resistant:** Meta-fitness uses Cohen's d (effect size) to prevent the optimizer from cheating by inflating scores
- **5-axis structural fitness:** RAW chain depth, load-after-store hazards, opcode diversity, branch polarity, and balance
- **Weight-free alternative:** NSGA-II produces a 30-genome Pareto front (eliminates weights entirely)
- **Statistically validated:** 12 seeds, Welch's t-test, Cohen's d = 2.0, p = 0.000132

## Results

| Metric | Random Stimulus | DASE Framework |
|---|:---:|:---:|
| Mean Structural Fitness | 0.771 | 0.861 |
| 95% Confidence Interval | (0.740, 0.803) | (0.844, 0.878) |
| Statistical Significance | — | Significant (p=0.000132) |
| Effect Size (Cohen's d) | — | 2.0 (very large) |
| Unique Opcodes | 7 | 13 |
| Register Coverage | Low | High |
| Pipeline Stage Coverage | Partial | Balanced |
| Simulation Throughput | — | 32.12 IPS |

## Architecture

```
OUTER LOOP: CMA-ES (The Self-Tuner)
  Evolves: 5 weights + 3 ceilings (8 parameters)
  Meta-fitness: Cohen's d (gaming-resistant)
  Iterations: 100 function evaluations

  INNER LOOP: DASE GA (The Test Program Evolver)
    Evolves: 4-gene genome (raw, hazard, opcode, branch)
    Population: 8 | Generations: 25 | Seeds: 12

    Genome -> Program -> Compile -> Simulate -> Coverage ->
    Fitness -> Roulette Selection -> Crossover -> Mutation ->
    Loop back (25 generations)
```

## The Genome

Each test program is described by a 4-gene integer genome:

| Gene | Name | Controls | Default Ceiling |
|---|---|---|---|
| 1 | raw | Number of instructions in the RAW dependency chain | 80 |
| 2 | hazard | Number of load-after-store hazard pairs | 15 |
| 3 | opcode | Number of diverse instructions in the opcode block | 8 |
| 4 | branch | Number of instructions in the branch loop | binary |

## Fitness Function

```
F = w1*R + w2*H + w3*O + w4*B + w5*Balance

Where:
  R = min(RAW_depth / Rmax, 1.0)          - RAW chain score
  H = min(HAZ_count / Hmax, 1.0)          - Hazard score
  O = unique_opcodes / opcode_universe     - Opcode diversity
  B = min(taken, not_taken) / max(taken, not_taken + eps)  - Branch polarity
  Balance = 1 - sigma   (sigma = standard deviation of R, H, O, B)

Default weights: [0.40, 0.25, 0.15, 0.10, 0.10]
CMA-ES evolved:  [0.376, 0.444, 0.074, 0.057, 0.049]
```

## Installation

### Python Dependencies

```
pip install numpy scipy pyyaml cma matplotlib
```

### Optional: Real-sim mode (requires RISC-V toolchain)

```
sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf \
                 iverilog make coreutils
pip install cocotb
```

## Quickstart

```
# Clone the repository
git clone https://github.com/yourusername/dase.git
cd dase

# Install dependencies
pip install -r requirements.txt

# Run the full DASE experiment (12 seeds, 25 generations)
python3 agent/coverage_closure.py

# Run CMA-ES self-tuning (evolves the fitness weights)
python3 agent/self_tune.py --seed 42 --cma-fevals 100 --meta-seeds 6

# Table 1 reproduction only (locked weights, no CMA-ES)
python3 agent/self_tune.py --seed 42 --seeds 12 --cma-fevals 0
```

### Expected Output

```
========== FINAL STATISTICS ==========
DASE Mean:   0.861
Random Mean: 0.771
DASE CI:     (0.844, 0.878)
Random CI:   (0.740, 0.803)
Cohen's d:   2.0
t-stat:      4.808
p-value:     0.000132
Statistically significant
```

## Configuration

All knobs are in config.yaml:

```yaml
inner:
  generations: 25
  population: 8
  seeds: 12
  mutation_rate: 0.3
  crossover_rate: 0.7
  elitism_k: 2

weights:
  raw: 0.40
  hazard: 0.25
  opcode: 0.15
  branch: 0.10
  balance: 0.10

ceilings:
  raw: 80.0
  hazard: 15.0
  opcode: 8.0

cma_es:
  max_fevals: 100
  sigma0: 0.6
  meta_seeds: 6
```

## Project Structure

```
dase/
├── config.yaml                          All tunable knobs
├── requirements.txt                     Python dependencies
├── RUN.md                               Run instructions
├── agent/
│   ├── coverage_closure.py              DASE inner loop (GA: roulette + crossover)
│   └── self_tune.py                     CMA-ES meta-optimizer
├── test_results/
│   ├── multi_seed_results.json          Aggregated results (3 outer seeds)
│   ├── tuning_results.json              CMA-ES evolved weights
│   ├── slide_43_fitness_progression.png Fitness progression graph
│   ├── slide_45_instruction_diversity.png Opcode diversity graph
│   ├── slide_48_side_by_side.png        Comparison bar chart
│   └── flowchart.png                    Corrected flow diagram
└── docs/
    ├── DASE_DVCon_Presentation_v1.2.pdf  Presentation (55 slides)
    ├── DASE_DVCon_Presentation_v1.2.pptx Editable presentation
    ├── DASE_Complete_Project_Documentation.docx Full A-to-Z documentation
    ├── DASE_Speaker_Script_All_Slides.docx     Speaker notes for all slides
    └── DASE_DVCon_QA_with_Answers.docx        150 Q&A with answers
```

## Algorithm

### Algorithm 1: DASE Main Loop (GA)

```
Phase I: Initialization
  1: P <- InitializePopulation(N=8)
  2: For each genome in P:
  3:   Generate assembly -> Compile -> Simulate -> Extract coverage
  4:   Compute fitness F
  5: End for

Phase II: Evolution (25 generations)
  6: For generation = 1 to G:
  7:   Elitism: keep top K=2 genomes unchanged
  8:   While population < N:
  9:     RouletteSelect Parent 1 (P_i = F_i / Sum(F_j))
  10:    RouletteSelect Parent 2
  11:    Crossover (p=0.7): combine parent genes
  12:    Mutation (p=0.3): add random delta (biased toward growth)
  13:    Evaluate child: compile, simulate, compute fitness
  14:    Insert child into new population
  15:  End while
  16:  Replace population
  17: End for
  18: Return best genome
```

### Algorithm 2: Structural Fitness

```
Input: Coverage metrics {RAW, HAZ, OPC, BR}, Weights w1..w5
Output: Fitness score F in [0, 1]

1: R <- min(RAW_depth, Rmax) / Rmax
2: H <- min(HAZ_count, Hmax) / Hmax
3: O <- unique_opcodes / opcode_universe
4: B <- min(BranchesTaken, BranchesNotTaken) / max(BranchesTaken, BranchesNotTaken + eps)
5: mu <- (R + H + O + B) / 4
6: sigma <- sqrt(((R-mu)^2 + (H-mu)^2 + (O-mu)^2 + (B-mu)^2) / 4)
7: Balance <- 1 - sigma
8: F <- w1*R + w2*H + w3*O + w4*B + w5*Balance
9: F <- clip(F, 0, 1)
10: return F
```

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Design Under Test | PicoRV32 (RV32I) | Open-source, public domain, real microarchitecture |
| Testbench | cocotb 2.0 | Python-based, same language as orchestrator |
| Simulator | Icarus Verilog 12.0 | Free, open-source, sufficient speed |
| Compiler | riscv64-unknown-elf-gcc | Standard RISC-V GCC toolchain |
| Orchestration | Python 3.12 | Developer time > runtime; rich ecosystem |
| Meta-optimizer | cma 4.4.4 (CMA-ES) | State-of-the-art continuous optimization |
| Statistics | scipy + numpy | Welch's t-test, Cohen's d |

## Authors

- Ankush Kumar Jaiswal - School of Electronics Engineering (SENSE), VIT Chennai
- Aarav Sharma - School of Electronics Engineering (SENSE), VIT Chennai
- Garvit Maheshwari - School of Electronics Engineering (SENSE), VIT Chennai
- Jean Jenifer Nesam - School of Electronics Engineering (SENSE), VIT Chennai

## License

- PicoRV32 (rtl/picorv32.v): Public domain, by Claire Wolf
- DASE code (agent/*.py, config.yaml): Project internal
- Documentation (.docx, .pdf): Free to use within project context

## References

1. Fine, S. and Ziv, A. - "Coverage Directed Test Generation using Bayesian Networks" (DAC 2003)
2. Laeufer, K. et al. - "RFUZZ: Coverage-Directed Fuzz Testing of RTL on FPGAs" (ICCAD 2018)
3. Squillero, G. - "MicroGP: An Evolutionary Assembly Program Generator"
4. Adir, A. et al. - "Functional verification of the IBM POWER4 microprocessor" (DAC 2003)
5. Piziali, B. - "Functional Verification Coverage Measurement and Analysis" (Springer, 2004)
6. Hansen, N. - "The CMA Evolution Strategy: A Tutorial" (arXiv:1604.00772)
7. Deb, K. et al. - "A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II" (IEEE TEVC, 2002)

## Related Work

- RFUZZ (FPGA-based coverage fuzzing)
- MicroGP (evolutionary assembly generation)
- MorFuzz (runtime instruction morphing)
- Lyra (FPGA-accelerated generative model fuzzing)

## Presented at

DVCon India 2026
