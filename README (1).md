<div align="center">

# RISC-V Single-Cycle Core

**A synthesizable 32-bit RISC-V (RV32I subset) single-cycle processor written in Verilog.**

[![Language: Verilog](https://img.shields.io/badge/language-Verilog-blue.svg)](#tech-stack)
[![ISA: RISC-V RV32I subset](https://img.shields.io/badge/ISA-RV32I%20(subset)-orange.svg)](#supported-instructions)
[![Simulator: Icarus Verilog](https://img.shields.io/badge/sim-Icarus%20Verilog-green.svg)](#prerequisites)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-lightgrey.svg)](#license)
[![Build Status](https://img.shields.io/badge/build-[BUILD_BADGE_URL]-lightgrey.svg)](#)

*Developed by [MERL-DSU](https://github.com/merldsu) — Accelerating Engineering Innovation*

</div>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Supported Instructions](#supported-instructions)
- [Architecture](#architecture)
  - [Datapath](#datapath)
  - [Control Unit](#control-unit)
  - [ALU](#alu)
  - [Module Reference](#module-reference)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Usage / Quick Start](#usage--quick-start)
  - [Running the Testbench](#running-the-testbench)
  - [Viewing Waveforms](#viewing-waveforms)
  - [Default Demo Program](#default-demo-program)
  - [Loading Your Own Program](#loading-your-own-program)
- [Configuration](#configuration)
- [Module Interfaces (Core API)](#module-interfaces-core-api)
- [Known Limitations](#known-limitations)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This repository contains the design files for a **RISC-V single-cycle microprocessor core**. Every instruction is fetched, decoded, executed, and written back within a **single clock cycle**, making the design an ideal reference for learning computer architecture, validating datapath/control concepts, or serving as a starting point for a pipelined implementation.

The microarchitecture follows the classic textbook decomposition:

1. **State elements** — Program Counter, Instruction Memory, Register File, Data Memory.
2. **Combinational logic** — ALU, Sign Extender, multiplexers, PC adder.
3. **Control Unit** — a two-level decoder (Main Decoder + ALU Decoder) that derives all control signals from `opcode`, `funct3`, and `funct7`.

A companion design document, *RISC-V Single Cycle Microarchitecture* (MERL-DSU), walks through the ALU, control unit, and step-by-step datapath construction for `lw`, `sw`, and R-type instructions.

---

## Key Features

- **32-bit datapath** with a 32 × 32-bit register file (two read ports, one write port).
- **Single-cycle execution** — one instruction per clock, CPI = 1.
- **Modular, hierarchical Verilog** — one module per file, with a single top-level (`Single_Cycle_Top`).
- **Two-level control unit** — `Main_Decoder` produces control signals and `ALUOp`; `ALU_Decoder` refines it into a 3-bit `ALUControl`.
- **Full ALU status flags** — `Zero`, `Negative`, `Carry`, and `OverFlow` are generated.
- **Self-contained testbench** with VCD dump and a pre-saved GTKWave layout.
- **Active-low synchronous-style reset** across all state elements.

---

## Supported Instructions

| Format | Instruction | Opcode | `funct3` | `funct7[5]` | ALU Operation |
|:------:|:-----------:|:------:|:--------:|:-----------:|:--------------|
| I-type | `lw`        | `0000011` | `010` | — | Add (base + offset) |
| S-type | `sw`        | `0100011` | `010` | — | Add (base + offset) |
| R-type | `add`       | `0110011` | `000` | `0` | Add |
| R-type | `sub`       | `0110011` | `000` | `1` | Subtract |
| R-type | `slt`       | `0110011` | `010` | — | Set less than |
| R-type | `or`        | `0110011` | `110` | — | Bitwise OR |
| R-type | `and`       | `0110011` | `111` | — | Bitwise AND |

> **Note:** `beq` is decoded by the control unit (`Branch`, `ALUOp = 01`) but branching is **not yet wired into the top-level datapath**. See [Known Limitations](#known-limitations).

---

## Architecture

### Datapath

```
                 ┌────────────────────────── PCPlus4 ──────────────────────────┐
                 │                                                             │
            ┌────▼───┐   ┌──────────────┐   ┌───────────────┐       ┌──────────┴─┐
   clk,rst ►│   PC   ├──►│ Instruction  ├──►│ Register File │──RD1─►│            │   ┌─────────────┐
            └────┬───┘   │   Memory     │   │  A1 A2 A3 WD3 │       │    ALU     ├──►│ Data Memory ├─┐
                 │       └──────┬───────┘   └──┬────────▲───┘  ┌───►│            │   └─────────────┘ │
            ┌────▼───┐          │              │RD2     │      │    └─────▲──────┘                   │
            │ PC+4   │          │         ┌────▼────┐   │      │          │ALUControl                │
            └────────┘          ├────────►│ ALUSrc  ├───┼──────┘          │                    ┌─────▼─────┐
                                │ imm     │   Mux   │   │                 │                    │ ResultSrc │
                                │         └────▲────┘   │                 │                    │    Mux    │
                                │         ┌────┴────┐   └────── Result ◄──┼────────────────────┤           │
                                └────────►│  Sign   │                     │                    └───────────┘
                                          │ Extend  │            ┌────────┴────────┐
                                          └─────────┘            │  Control Unit   │◄── opcode / funct3 / funct7
                                                                 └─────────────────┘
```

- **Instruction fetch:** `PC` → `Instruction_Memory` (word-addressed using `PC[31:2]`); `PC_Adder` computes `PC + 4`.
- **Decode / register read:** `rs1 = Instr[19:15]`, `rs2 = Instr[24:20]`, `rd = Instr[11:7]`.
- **Execute:** the `ALUSrc` mux selects `SrcB` from `RD2` (R-type) or the sign-extended immediate (`lw`/`sw`).
- **Memory:** ALU result is the data-memory address; `RD2` is the store data.
- **Write-back:** the `ResultSrc` mux selects between `ALUResult` (R-type) and `ReadData` (`lw`).

### Control Unit

**Main Decoder** (function of `Op[6:0]`):

| Instruction | Op        | RegWrite | ImmSrc | ALUSrc | MemWrite | ResultSrc | Branch | ALUOp |
|:-----------:|:---------:|:--------:|:------:|:------:|:--------:|:---------:|:------:|:-----:|
| `lw`        | `0000011` | 1 | `00` | 1 | 0 | 1 | 0 | `00` |
| `sw`        | `0100011` | 0 | `01` | 1 | 1 | 0 | 0 | `00` |
| R-type      | `0110011` | 1 | `00` | 0 | 0 | 0 | 0 | `10` |
| `beq`       | `1100011` | 0 | `10` | 0 | 0 | 0 | 1 | `01` |

**ALU Decoder** (function of `ALUOp`, `funct3`, `{Op[5], funct7[5]}`):

| ALUOp | funct3 | {op₅, funct7₅} | ALUControl | Instruction |
|:-----:|:------:|:--------------:|:----------:|:-----------:|
| `00`  | x   | x            | `000` (add)      | `lw`, `sw` |
| `01`  | x   | x            | `001` (subtract) | `beq` |
| `10`  | `000` | `00`, `01`, `10` | `000` (add)      | `add` |
| `10`  | `000` | `11`         | `001` (subtract) | `sub` |
| `10`  | `010` | x            | `101` (set less than) | `slt` |
| `10`  | `110` | x            | `011` (or)       | `or` |
| `10`  | `111` | x            | `010` (and)      | `and` |

### ALU

The ALU takes two 32-bit operands (`A`, `B`) and a 3-bit `ALUControl`, and produces a 32-bit `Result` plus status flags.

| `ALUControl` | Operation | Result |
|:------------:|:----------|:-------|
| `000` | Add | `A + B` |
| `001` | Subtract | `A - B` (computed as `A + ~B + 1`) |
| `010` | AND | `A & B` |
| `011` | OR | `A \| B` |
| `101` | Set less than | `{31'b0, Sum[31]}` |
| others | Undefined | `0` |

`ALUControl[0]` selects add vs. subtract, `ALUControl[1]` selects arithmetic vs. logic group, and `ALUControl[2]` selects the `slt` post-processing.

**Flags:** `Zero` (all result bits are 0), `Negative` (`Result[31]`), `Carry`, and `OverFlow`.

### Module Reference

| File | Module | Description |
|------|--------|-------------|
| `src/Single_Cycle_Top.v` | `Single_Cycle_Top` | Top-level; wires every submodule together. |
| `src/PC.v` | `PC_Module` | 32-bit program counter register with active-low reset. |
| `src/PC_Adder.v` | `PC_Adder` | 32-bit adder used for `PC + 4`. |
| `src/Instruction_Memory.v` | `Instruction_Memory` | 1024 × 32-bit combinational-read instruction ROM. |
| `src/Register_File.v` | `Register_File` | 32 × 32-bit register file, 2 async read ports, 1 sync write port. |
| `src/Sign_Extend.v` | `Sign_Extend` | Builds the 32-bit immediate for I-type and S-type formats. |
| `src/Mux.v` | `Mux` | Generic 2-to-1, 32-bit multiplexer (used twice). |
| `src/ALU.v` | `ALU` | Arithmetic/logic unit with `Zero`/`Negative`/`Carry`/`OverFlow` flags. |
| `src/Control_Unit_Top.v` | `Control_Unit_Top` | Wraps the Main and ALU decoders. |
| `src/Main_Decoder.v` | `Main_Decoder` | Opcode → control signals + `ALUOp`. |
| `src/ALU_Decoder.v` | `ALU_Decoder` | `ALUOp` + funct fields → `ALUControl`. |
| `src/Data_Memory.v` | `Data_Memory` | 1024 × 32-bit data RAM; synchronous write, combinational read. |
| `src/Single_Cycle_Top_Tb.v` | `Single_Cycle_Top_Tb` | Testbench: clock, reset, and VCD dump. |

---

## Tech Stack

| Category | Tool / Technology |
|----------|-------------------|
| HDL | Verilog (IEEE 1364) |
| Simulation | [Icarus Verilog](https://steveicarus.github.io/iverilog/) (`iverilog` / `vvp`) |
| Waveform Viewer | [GTKWave](https://gtkwave.sourceforge.net/) |
| ISA | RISC-V RV32I (subset) |

---

## Repository Structure

```
RISCV_Single_Cycle_Core/
├── README.md
├── memfile.hex                 # Example program image (OR / AND) — not loaded by default
└── src/
    ├── Single_Cycle_Top.v      # Top-level design
    ├── Single_Cycle_Top_Tb.v   # Testbench
    ├── PC.v
    ├── PC_Adder.v
    ├── Instruction_Memory.v
    ├── Register_File.v
    ├── Sign_Extend.v
    ├── Mux.v
    ├── ALU.v
    ├── Control_Unit_Top.v
    ├── Main_Decoder.v
    ├── ALU_Decoder.v
    ├── Data_Memory.v
    ├── memfile.hex             # Example program image (matches default demo) — not loaded by default
    ├── waveform.gtkw           # Saved GTKWave signal layout
    ├── Single Cycle.vcd        # Sample simulation dump
    └── sim.out                 # Sample compiled simulation output
```

> `Single_Cycle_Top.v` pulls in all other design modules via `` `include `` directives, so only the top-level and testbench need to be passed to the compiler.

---

## Prerequisites

| Dependency | Purpose | Notes |
|------------|---------|-------|
| **Icarus Verilog** (`iverilog`, `vvp`) | Compile and run the simulation | Any recent release should work. |
| **GTKWave** | View `.vcd` waveforms | Optional, but recommended. |
| **Git** | Clone the repository | — |

Install on common platforms:

```bash
# Debian / Ubuntu
sudo apt-get install iverilog gtkwave

# macOS (Homebrew)
brew install icarus-verilog
brew install --cask gtkwave

# Windows
# Install Icarus Verilog + GTKWave from their official installers,
# or use WSL and follow the Debian / Ubuntu instructions above.
```

---

## Installation & Setup

1. **Clone the repository**

   ```bash
   git clone [REPO_URL]
   cd RISCV_Single_Cycle_Core
   ```

2. **Verify your toolchain**

   ```bash
   iverilog -V
   vvp -V
   ```

3. **Move into the source directory**

   ```bash
   cd src
   ```

No build system, package manager, or environment variables are required.

---

## Usage / Quick Start

### Running the Testbench

From the `src/` directory:

```bash
# 1. Compile (the top-level `include`s every design module)
iverilog -o sim.out Single_Cycle_Top_Tb.v Single_Cycle_Top.v

# 2. Simulate
vvp sim.out
```

This produces `Single Cycle.vcd` in the current directory (note the space in the filename).

**Testbench timing** (`Single_Cycle_Top_Tb.v`):

| Event | Time |
|-------|------|
| Clock period | 100 time units (toggles every 50) |
| Reset asserted (`rst = 0`, active-low) | `0 – 150` |
| Reset released (`rst = 1`) | `150` |
| Simulation ends (`$finish`) | `600` |

### Viewing Waveforms

```bash
gtkwave "Single Cycle.vcd" waveform.gtkw
```

> `waveform.gtkw` was saved with an absolute Windows path to the VCD file. If GTKWave cannot locate the dump, open `Single Cycle.vcd` manually and use **File → Read Save File** to load `waveform.gtkw`.

### Default Demo Program

The program is hard-coded in the `initial` block of `src/Instruction_Memory.v`:

| Address | Machine Code | Assembly | Effect |
|:-------:|:------------:|:---------|:-------|
| `0x00` | `00500293` | `addi x5, x0, 5` | *No effect — see [Known Limitations](#known-limitations)* |
| `0x04` | `00400313` | `addi x6, x0, 4` | *No effect — see [Known Limitations](#known-limitations)* |
| `0x08` | `006283B3` | `add  x7, x5, x6` | `x7 = 5 + 4 = 9` |
| `0x0C` | `406283B3` | `sub  x7, x5, x6` | `x7 = 5 - 4 = 1` |

`x5` and `x6` are pre-loaded with `5` and `4` by the `initial` block in `Register_File.v`, so the `add`/`sub` results are correct even though the `addi` instructions are not executed by this core.

**Expected observation:** after reset is released, `x7` becomes `9` following the `add` (cycle at `PC = 0x08`), then `1` following the `sub` (cycle at `PC = 0x0C`).

### Loading Your Own Program

Edit the `initial` block in `src/Instruction_Memory.v` and assign 32-bit instruction words by **word index** (`mem[0]` is address `0x00`, `mem[1]` is `0x04`, …):

```verilog
initial begin
    mem[0] = 32'h[INSTRUCTION_0];
    mem[1] = 32'h[INSTRUCTION_1];
    // ...
end
```

Alternatively, enable the commented-out `$readmemh` block in the same file to load a hex image:

```verilog
initial begin
    $readmemh("memfile.hex", mem);
end
```

The `.hex` files in this repository use the `@00000000` address-marker format followed by one 32-bit hex word per line. Run the simulator from the directory containing the hex file (or use a path relative to it).

To pre-seed registers or data memory, edit the `initial` blocks in `Register_File.v` and `Data_Memory.v` respectively.

---

## Configuration

This project has **no environment variables, secrets, or external configuration files**. All parameters are set directly in the HDL:

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| Program contents | `src/Instruction_Memory.v` (`initial` block) | 4-instruction demo | Instruction image. |
| Instruction memory depth | `src/Instruction_Memory.v` (`mem`) | 1024 words | 4 KiB of instruction storage. |
| Data memory depth | `src/Data_Memory.v` (`mem`) | 1024 words | 4 KiB of data storage. |
| Initial register values | `src/Register_File.v` (`initial` block) | `x5 = 5`, `x6 = 4` | Pre-loaded for the demo. |
| Initial data memory | `src/Data_Memory.v` (`initial` block) | `mem[28] = 0x20` | Pre-loaded word. |
| Clock period | `src/Single_Cycle_Top_Tb.v` | 100 time units | Edit the `#50` delay in the clock `always` block. |
| Reset duration / run length | `src/Single_Cycle_Top_Tb.v` | 150 / 600 time units | Edit the `#150` and `#450` delays. |
| Waveform output | `src/Single_Cycle_Top_Tb.v` | `Single Cycle.vcd` | `$dumpfile` argument. |

---

## Module Interfaces (Core API)

### `Single_Cycle_Top`

| Port | Dir | Width | Description |
|------|-----|:-----:|-------------|
| `clk` | in | 1 | System clock (rising-edge triggered). |
| `rst` | in | 1 | **Active-low** reset. |

### `ALU`

| Port | Dir | Width | Description |
|------|-----|:-----:|-------------|
| `A`, `B` | in | 32 | Operands. |
| `ALUControl` | in | 3 | Operation select (see [ALU](#alu)). |
| `Result` | out | 32 | Operation result. |
| `Zero` | out | 1 | High when `Result == 0`. |
| `Negative` | out | 1 | `Result[31]`. |
| `Carry` | out | 1 | Carry-out (arithmetic ops only). |
| `OverFlow` | out | 1 | Signed overflow (arithmetic ops only). |

### `Control_Unit_Top`

| Port | Dir | Width | Description |
|------|-----|:-----:|-------------|
| `Op` | in | 7 | `Instr[6:0]` |
| `funct3` | in | 3 | `Instr[14:12]` |
| `funct7` | in | 7 | `Instr[31:25]` |
| `RegWrite`, `ALUSrc`, `MemWrite`, `ResultSrc`, `Branch` | out | 1 | Control signals. |
| `ImmSrc` | out | 2 | Immediate format select. |
| `ALUControl` | out | 3 | ALU operation select. |

### `Register_File`

| Port | Dir | Width | Description |
|------|-----|:-----:|-------------|
| `clk`, `rst` | in | 1 | Clock / active-low reset (reset forces read ports to 0). |
| `A1`, `A2` | in | 5 | Read-port addresses. |
| `A3` | in | 5 | Write-port address. |
| `WD3` | in | 32 | Write data. |
| `WE3` | in | 1 | Write enable (writes on rising clock edge). |
| `RD1`, `RD2` | out | 32 | Read data (combinational). |

### `Data_Memory`

| Port | Dir | Width | Description |
|------|-----|:-----:|-------------|
| `clk`, `rst` | in | 1 | Clock / active-low reset (reset forces `RD` to 0). |
| `A` | in | 32 | Address (used directly as a **word index**). |
| `WD` | in | 32 | Write data. |
| `WE` | in | 1 | Write enable (writes on rising clock edge). |
| `RD` | out | 32 | Read data (combinational). |

### `Instruction_Memory`

| Port | Dir | Width | Description |
|------|-----|:-----:|-------------|
| `rst` | in | 1 | Active-low reset (forces `RD` to 0). |
| `A` | in | 32 | Byte address; indexes memory with `A[31:2]`. |
| `RD` | out | 32 | Instruction word (combinational). |

---

## Known Limitations

This core is a learning/reference implementation. Please be aware of the following behaviors in the current source:

| # | Limitation | Detail |
|:-:|------------|--------|
| 1 | **Branches are not implemented in the datapath** | `Main_Decoder` decodes `beq` and asserts `Branch`, but `Single_Cycle_Top` leaves `Branch`, and the ALU `Zero` flag unconnected. There is no `PCSrc` logic or branch-target adder, so the PC always advances by `+4`. |
| 2 | **B-type immediates are not generated** | `Sign_Extend` receives only `ImmSrc[0]`, so it handles I-type and S-type formats only. |
| 3 | **I-type ALU instructions (`addi`, `andi`, …) are not decoded** | Opcode `0010011` is not recognized by `Main_Decoder`, so `RegWrite` stays low. In the demo program, the two `addi` instructions are therefore no-ops, and `x5`/`x6` are seeded in `Register_File.v` instead. |
| 4 | **Data memory is word-indexed by the raw address** | `Data_Memory` uses `mem[A]` rather than `mem[A[31:2]]`, so addresses are treated as word indices rather than byte addresses. Instruction memory, by contrast, correctly uses `A[31:2]`. |
| 5 | **No sub-word access** | Only `lw`/`sw` are supported; `lb`, `lh`, `lbu`, `lhu`, `sb`, `sh` are not. |
| 6 | **`x0` is not hard-wired to zero** | `Register_File` allows writes to register 0. |
| 7 | **`slt` ignores signed overflow** | The result is taken from `Sum[31]` directly, so it can be incorrect when the subtraction overflows. |
| 8 | **Shift, XOR, `slti`/`sltu`, LUI/AUIPC, JAL/JALR are unsupported** | These appear in the reference tables of the design document but are outside the implemented subset. |
| 9 | **Program loaded via hard-coded `initial` block** | The `$readmemh` path is commented out; the bundled `memfile.hex` files are not read by default. |
| 10 | **Status flags unused at top level** | `Carry`, `OverFlow`, `Zero`, and `Negative` are generated by the ALU but not connected in `Single_Cycle_Top`. |

Contributions that close any of these gaps are welcome (see below).

---

## Documentation

The accompanying design document, **"RISC-V Single Cycle Microarchitecture"** (MERL-DSU, 21 pages), covers:

| Section | Topic |
|---------|-------|
| 1 | Arithmetic Logic Unit — operation table, block diagram, flag generation |
| 2 | Control Unit — R/I/S/B instruction formats, Main Decoder and ALU Decoder truth tables |
| 3 | Microarchitecture I — state elements (PC, register file, memories) and the RISC-V register map |
| 4 | Microarchitecture II — datapath for `lw`, immediate sign extension |
| 5 | Microarchitecture III — datapath extension for `sw` |
| 6 | Microarchitecture IV — datapath extension for R-type instructions |

Place the PDF in a `docs/` folder and link it here: **[DOCS_LINK]**

---

## Contributing

Contributions are welcome! To propose a change:

1. **Fork** the repository.
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**, following the existing conventions:
   - One module per file, file name matching the module (e.g. `ALU.v` → `module ALU`).
   - Keep new design files `` `include ``-able from `Single_Cycle_Top.v`.
   - Use the active-low `rst` convention for state elements.
4. **Verify** that the testbench still compiles and runs cleanly:
   ```bash
   cd src
   iverilog -o sim.out Single_Cycle_Top_Tb.v Single_Cycle_Top.v && vvp sim.out
   ```
5. **Commit** with a clear message and **push** your branch.
6. **Open a Pull Request** describing what changed and why, including waveform evidence or testbench output where relevant.

Good first contributions: wiring up `beq` (branch adder + `PCSrc`), adding B-type immediate decoding, supporting `addi`/I-type ALU ops, fixing the data-memory byte addressing, or adding a self-checking testbench.

Please open an issue first for larger architectural changes.

---

## License

Copyright 2023 MERL-DSU

Licensed under the **Apache License, Version 2.0** (the "License"); you may not use this project except in compliance with the License. You may obtain a copy of the License at

> <http://www.apache.org/licenses/LICENSE-2.0>

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

---

<div align="center">

*Built by [MERL-DSU](https://github.com/merldsu) — Accelerating Engineering Innovation*

</div>
