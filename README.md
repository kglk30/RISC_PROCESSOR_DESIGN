# RISC201 Processor Design & Simulation Framework

An advanced, cycle-accurate computer architecture and processor simulation environment based on **Prof. Smruti R. Sarangi's** textbooks (*Basic Computer Architecture* / *Computer Organisation and Architecture*, commonly referenced as `archbook`).

---

## Table of Contents
1. [Overview & Architectural Highlights](#overview--architectural-highlights)
2. [Instruction Set Architecture (RISC201)](#instruction-set-architecture-risc201)
3. [Implemented Architectural Modifications](#implemented-architectural-modifications)
   - [1. Hardwired Zero Register (r0)](#1-hardwired-zero-register-r0)
   - [2. Hardware Performance Monitoring Counters (PMCs)](#2-hardware-performance-monitoring-counters-pmcs)
   - [3. Active ASCII Stack Memory Visualizer](#3-active-ascii-stack-memory-visualizer)
   - [4. Control and Status Registers (CSRs)](#4-control-and-status-registers-csrs)
   - [5. Stack Canaries & Boundary Protection](#5-stack-canaries--boundary-protection)
   - [6. Dynamic 2-bit Saturating Counter Branch Predictor & BTB](#6-dynamic-2-bit-saturating-counter-branch-predictor--btb)
   - [7. Full-Matrix Multiplexer Forwarding Network](#7-full-matrix-multiplexer-forwarding-network)
   - [8. Leaf Function Optimization](#8-leaf-function-optimization)
4. [Pipeline Implementations: 4-Stage vs. 6-Stage](#pipeline-implementations-4-stage-vs-6-stage)
5. [Microprogrammed Control Unit (Horizontal vs. Vertical)](#microprogrammed-control-unit-horizontal-vs-vertical)
6. [Optimized ALU Subsystem](#optimized-alu-subsystem)
7. [Software Suite & Toolchain](#software-suite--toolchain)
8. [CLI & Debugger Usage Guide](#cli--debugger-usage-guide)
9. [Empirical Benchmarks & Experimental Results](#empirical-benchmarks--experimental-results)

---

## Overview & Architectural Highlights

The **RISC201** simulation framework is a complete software hardware-modeling suite that includes:
* **Two-Pass Assembler** with macro expansion for full-descending stack operations.
* **Instruction Disassembler** parsing binary strings and hex machine words.
* **Dual Pipelined Processors**:
  * **4-Stage Pipeline**: `IF` $\to$ `ID/OF` $\to$ `EX/MEM` $\to$ `WB`
  * **6-Stage Pipeline**: `IF` $\to$ `ID` $\to$ `RR` $\to$ `EX` $\to$ `MEM` $\to$ `WB`
* **Microprogrammed Control Unit** featuring both **Horizontal** (wide unencoded) and **Vertical** (narrow encoded with micro-decoders) Control Store ROMs.
* **Interactive CLI Debugger** with an **Active ASCII Stack Frame Visualizer**, pipeline stage inspector, and cycle-by-cycle stepping.

```
       ┌────────────────────────────────────────────────────────┐
       │              RISC201 Simulation Framework              │
       └───────────────────────────┬────────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
  ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
  │   4-Stage    │          │   6-Stage    │          │Microprogram  │
  │   Pipeline   │          │   Pipeline   │          │ Control Unit │
  └──────┬───────┘          └──────┬───────┘          └──────┬───────┘
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
  ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
  │  Full-Matrix │          │ Dynamic 2-bit│          │ Stack Canary │
  │  Forwarding  │          │  Branch BTB  │          │  & CSR Traps │
  └──────────────┘          └──────────────┘          └──────────────┘
```

---

## Instruction Set Architecture (RISC201)

RISC201 uses a 32-bit fixed-width instruction format following SimpleRisc specifications:

### 1. Instruction Formats
```
Register Format (I=0):
[31:27 Opcode (5b)] [26 I=0 (1b)] [25:22 rd (4b)] [21:18 rs1 (4b)] [17:14 rs2 (4b)] [13:0 Unused (14b)]

Immediate Format (I=1):
[31:27 Opcode (5b)] [26 I=1 (1b)] [25:22 rd (4b)] [21:18 rs1 (4b)] [17:0 Immediate (18b signed)]

Branch Format:
[31:27 Opcode (5b)] [26:0 Branch Offset (27b signed, word-relative)]

Trap Format:
[31:27 Opcode 10111 (5b)] [26:0 Trap Vector ID (27b)]
```

### 2. Opcode Table
| Opcode (Binary) | Name | Syntax | Description |
|---|---|---|---|
| `00000` (0)  | `add`  | `add rd, rs1, rs2/imm` | Addition: $rd = rs1 + (rs2 \text{ or } imm)$ |
| `00001` (1)  | `sub`  | `sub rd, rs1, rs2/imm` | Subtraction: $rd = rs1 - (rs2 \text{ or } imm)$ |
| `00010` (2)  | `mul`  | `mul rd, rs1, rs2/imm` | Multiplication: $rd = rs1 \times (rs2 \text{ or } imm)$ |
| `00011` (3)  | `div`  | `div rd, rs1, rs2/imm` | Integer Division: $rd = rs1 / (rs2 \text{ or } imm)$ |
| `00100` (4)  | `mod`  | `mod rd, rs1, rs2/imm` | Modulo Remainder: $rd = rs1 \pmod{rs2 \text{ or } imm}$ |
| `00101` (5)  | `cmp`  | `cmp rs1, rs2/imm`     | Compare operands, update flags (Z, N, C, V) |
| `00110` (6) | `and` | `and rd, rs1, rs2/imm` | Bitwise AND: `rd = rs1 & (rs2 or imm)` |
| `00111` (7)  | `or`   | `or rd, rs1, rs2/imm`  | Bitwise OR: $rd = rs1 \ \| \ (rs2 \text{ or } imm)$ |
| `01000` (8)  | `not`  | `not rd, rs1`          | Bitwise NOT: $rd = \sim rs1$ |
| `01001` (9)  | `mov`  | `mov rd, rs1/imm`      | Move register or immediate value into $rd$ |
| `01010` (10) | `lsl`  | `lsl rd, rs1, rs2/imm` | Logical Shift Left: $rd = rs1 \ll (rs2 \text{ or } imm)$ |
| `01011` (11) | `lsr`  | `lsr rd, rs1, rs2/imm` | Logical Shift Right: $rd = rs1 \gg (rs2 \text{ or } imm)$ |
| `01100` (12) | `asr`  | `asr rd, rs1, rs2/imm` | Arithmetic Shift Right (sign-preserving) |
| `01101` (13) | `nop`  | `nop`                  | No operation |
| `01110` (14) | `ld`   | `ld rd, imm[rs1]`      | Load 32-bit word from memory at $rs1 + imm$ |
| `01111` (15) | `st`   | `st rd, imm[rs1]`      | Store 32-bit word from $rd$ into memory at $rs1 + imm$ |
| `10000` (16) | `beq`  | `beq label`            | Branch if Equal ($Z = 1$) |
| `10001` (17) | `bgt`  | `bgt label`            | Branch if Greater ($Z = 0 \text{ and } N == V$) |
| `10010` (18) | `b`    | `b label`              | Unconditional Branch |
| `10011` (19) | `call` | `call label`           | Subroutine Call: saves $PC + 4$ in $ra$ (r15), jumps |
| `10100` (20) | `ret`  | `ret`                  | Subroutine Return: jumps to address in $ra$ (r15) |
| `10101` (21) | `blt`  | `blt label`            | Branch if Less ($N \neq V$) |
| `10110` (22) | `bne`  | `bne label`            | Branch if Not Equal ($Z = 0$) |
| `10111` (23) | `trap` | `trap id`              | Software interrupt / security exception |
| `11000` (24) | `clz` | `clz rd, rs1` | Count leading zeros in a 32-bit value (Python implementation) |
| `11001` (25) | `popcnt` | `popcnt rd, rs1` | Count set bits in a 32-bit value (Python implementation) |
| `11111` (31) | `hlt`  | `hlt`                  | Halt processor execution |

---

## Implemented Architectural Modifications

### 1. Hardwired Zero Register (`r0`)
* **Specification**: Register index 0 is hardwired to integer 0.
* **Implementation** (`risc201/core/registers.py`):
  * `read(0)` always returns `0`.
  * `write(0, value)` silently discards the write operation.
* **Benefit**: Eliminates redundant zero-initialization instructions, allows standard negation (`sub rd, r0, rs2`), and guarantees compatibility with modern RISC conventions (RISC-V, MIPS).

### 2. Hardware Performance Monitoring Counters (PMCs)
* **Specification**: Special-purpose hardware telemetry tracking cycle-by-cycle metrics.
* **Implementation** (`risc201/core/pmc.py`):
  * `cycle_count`, `instruction_count`, `stall_count`
  * `load_use_stalls`, `structural_stalls`, `forwarding_events`
  * `branch_count`, `branch_mispredict_count`
  * Dynamic Calculation: **CPI** ($\text{Cycles} / \text{Instructions}$), **IPC**, and **Branch Mispredict Rate (%)**.

### 3. Active ASCII Stack Memory Visualizer
* **Specification**: Real-time terminal visualization of the runtime stack frame during stepping or debugging pauses.
* **Implementation** (`risc201/ui/visualizer.py`):
  * Dynamically slices memory between Stack Pointer (`sp`) and Frame Pointer (`fp`).
  * Annotates stack addresses, raw hex, signed decimal, saved frame pointer, return address, and stack canaries.

```
┌────────────────────────────────────────────────────────────────────────┐
│                     ACTIVE ASCII STACK FRAME MAP                       │
├────────────┬────────────┬─────────────┬────────────────────────────────┤
│  Address   │  Hex Word  │ Signed Dec  │ Frame Annotation / Symbols     │
├────────────┼────────────┼─────────────┼────────────────────────────────┤
│ 0x00003FFC │ 0x00000005 │           5 │ Caller Slot / Arg #0           │
│ 0x00003FF8 │ 0x00000028 │          40 │ Saved RA (ret to 0x00000028)   │
│ 0x00003FF4 │ 0x00004000 │       16384 │ --> [FP] Saved Old FP          │
│ 0x00003FF0 │ 0x0001C0DE │      114910 │ --> [SP] 🛡️ Canary: (Valid)     │
└────────────┴────────────┴─────────────┴────────────────────────────────┘
 Stack Base: 0x00004000  |  SP: 0x00003FF0  |  FP: 0x00003FF4  |  Limit: 0x00003000
```

### 4. Control and Status Registers (CSRs)
* **Specification**: Protected architectural register file for runtime exceptions.
* **Registers**:
  * `EPC`: Exception Program Counter holding faulting PC.
  * `CAUSE`: Architectural cause code (Division by Zero, Illegal Instruction, Stack Overflow, Misaligned Access, Canary Corrupted).
  * `STATUS`: Bit 0 = IE (Interrupt Enable), Bit 1 = Mode (User/Supervisor), Bit 2 = EX (Exception Active).
  * `BADVADDR`: Bad virtual address that triggered memory/alignment faults.

### 5. Stack Canaries & Boundary Protection
* **Specification**: Security mechanism detecting buffer overflows.
* **Implementation** (`risc201/core/stack.py`):
  * Stack Preprocessor expands `enter` and `leave` macros.
  * During function prologue (`enter`), a constant canary (`0x0001C0DE`) is stored right below the saved frame pointer.
  * During function epilogue (`leave`), the canary is read and checked against the expected magic constant.
  * If the canary is modified (e.g. by a buffer overflow exploit), execution immediately traps into `trap 6` (`STACK_CANARY_CORRUPTED`), halting execution and capturing the faulting PC in `EPC`.
  * Also enforces hardware **Red Zone / Guard Page** protection at `0x00002C00 - 0x00002FFF` and checks against stack underflow (`sp > stack_base`).

### 6. Dynamic 2-bit Saturating Counter Branch Predictor & BTB
* **Specification**: Dynamic prediction minimizing branch penalty cycles.
* **Implementation** (`risc201/pipelines/branch_predictor.py`):
  * 4 states:
    * `00`: Strongly Not-Taken (SNT)
    * `01`: Weakly Not-Taken (WNT)
    * `10`: Weakly Taken (WT)
    * `11`: Strongly Taken (ST)
  * Branch Target Buffer (BTB) maps branch PC to predicted target address.
  * Dynamically updated on branch resolution in the pipeline.

### 7. Full-Matrix Multiplexer Forwarding Network
* **Specification**: Forwarding paths routing computed values across pipeline latches:
  * `EX-to-EX Forwarding`: Forward previous ALU result directly to next ALU input.
  * `MEM-to-EX Forwarding`: Forward loaded data or older ALU result to EX stage.
  * `WB-to-RR Forwarding`: Register file write-to-read bypass.
  * `MEM-to-MEM Forwarding`: Forward loaded data directly to store data input.
* **Load-Use Hazard Unit**: Inserts a 1-cycle stall bubble when a dependent instruction follows a load (`ld`).

### 8. Leaf Function Optimization
* **Topic**: Leaf function optimization
* **Specification**: Avoids saving the return address and frame pointer when safe.
* **Implementation** (`risc201/core/stack.py`):
  * **Leaf Subroutine Detection**: Identifies subroutines that make no nested subroutine calls (`call` instruction) and do not clobber the return address register (`ra` / `r15`).
  * **Omission of Saved Return Address**: Since a leaf function never executes a downstream `call`, hardware preserves the return address in `ra` intact throughout subroutine execution. Storing `ra` to stack RAM in the prologue (`st ra, 0[sp]`) and loading `ra` in the epilogue (`ld ra, 0[sp]`) is completely eliminated.
  * **Omission of Saved Frame Pointer**: Subroutines that do not require dynamic stack frame management safely bypass saving the caller's frame pointer (`st fp, 0[sp]`) and adjusting `fp`. The caller's `fp` remains unaffected.
  * **Macro & Assembly Syntax**:
    * Explicit Leaf Macros: `enter_leaf <local_bytes>` and `leave_leaf <local_bytes>`.
    * Parameterized Syntax: `enter <local_bytes>, leaf` and `leave <local_bytes>, leaf`.
    * Automatic Leaf Detection: Passing `optimize_leaf=True` to `StackPreprocessor` / `Assembler` performs whole-routine static analysis, automatically identifying non-calling functions and applying leaf optimization.
  * **Prologue & Epilogue Transformation**:
    ```assembly
    ; --- Standard Function Frame (8 prologue + 10 epilogue instructions, 6 memory ops) ---
    enter 0                 ; Saves RA, FP, Canary to stack (3 stores)
    ...
    leave 0                 ; Checks Canary, restores FP, RA from stack (3 loads), ret

    ; --- Leaf-Optimized Frame (0 memory ops, direct register execution) ---
    enter_leaf 0            ; Omits RA, FP, and Canary stack stores
    ...
    leave_leaf 0            ; Omits stack loads; returns directly via ret (ra)
    ```
* **Benefits & Trade-Offs**:
  * **Zero Stack Bus Traffic**: Completely eliminates 6 stack memory operations per function call.
  * **Execution Speedup**: Yields a **2.39x speedup** on function call overhead.
  * **Hardware Security Hardening**: Because `ra` is preserved in CPU registers rather than being pushed to RAM, it is immune to stack buffer overflow hijacking.

---

## Pipeline Implementations: 4-Stage vs. 6-Stage

| Dimension | 4-Stage Pipeline | 6-Stage Pipeline |
|---|---|---|
| **Pipeline Stages** | `IF` $\to$ `ID/OF` $\to$ `EX/MEM` $\to$ `WB` | `IF` $\to$ `ID` $\to$ `RR` $\to$ `EX` $\to$ `MEM` $\to$ `WB` |
| **Stage Separation** | Combined Decode + Operand Fetch; Combined EX + Memory Access | Independent Decode and Register Read; Dedicated Memory stage |
| **Branch Resolution** | Evaluated at Stage 2 (`ID/OF`) | Evaluated at Stage 4 (`EX`) |
| **Misprediction Penalty** | 1 flush cycle | 3 flush cycles |
| **Clock Frequency Potential** | Moderate (longer critical path in `EX/MEM`) | High (balanced stage delays) |
| **Pipeline Latches** | `IF_ID`, `ID_EX`, `EX_WB` | `IF_ID`, `ID_RR`, `RR_EX`, `EX_MEM`, `MEM_WB` |

---

## Microprogrammed Control Unit (Horizontal vs. Vertical)

The simulator includes an explicit Control Memory (ROM) and Micro-Program Counter (`uPC`) to execute RISC201 without hardwired logic:

```
                  ┌───────────────────┐
                  │    Macro PC / IR  │
                  └─────────┬─────────┘
                            │ Opcode
                            ▼
                  ┌───────────────────┐
                  │   Dispatch Table  │
                  └─────────┬─────────┘
                            │ Target uAddr
                            ▼
   ┌───────┐      ┌───────────────────┐
   │  uPC  ├─────►│Control Store (ROM)├─────► Datapath Signals
   └───▲───┘      └─────────┬─────────┘
       │                    │ Next uPC
       └────────────────────┘
```

* **Horizontal Model**:
  * Word Width: **28 bits**.
  * Unencoded individual bit lines directly driving datapath multiplexers and control signals.
  * Zero decoding delay.
* **Vertical Model**:
  * Word Width: **14 bits** (50% reduction in Control Store ROM size).
  * Encoded functional fields (`ALU_Func`, `Src_Sel`, `Dst_Sel`, `Mem_Ctrl`, `Seq_Ctrl`) decoded through micro-decoders.

---

## Optimized ALU Subsystem

The Python `ALU` class (`risc201/alu/alu.py`) provides configurable algorithmic models:
* **Multiplication** (using the existing `mul` opcode `00010`):
  * **Dadda Tree Multiplier**: The Python default; models partial-product reduction with a simulated latency of 6 cycles.
  * **Fast Multiplier**: Native 1-cycle 32-bit two's complement product.
  * **Booth's Radix-2 Multiplier**: 32-cycle step-by-step arithmetic recoding ($Q_0, Q_{-1}$ comparison, addition/subtraction, arithmetic right shift).
  * **Shift-and-Add Multiplier**: 32-cycle unsigned shift-and-accumulate logic.
* **Division** (using `div` opcode `00011` for the quotient and `mod` opcode `00100` for the remainder):
  * **SRT Radix-2 Divider**: The Python default; uses a non-restoring-style radix-2 algorithm with a simulated latency of 32 cycles. SRT is an ALU algorithm, not a separate instruction or opcode.
  * **Fast Divider**: Native 1-cycle truncating division.
  * **Restoring Divider**: 32-cycle register shifting, trial subtraction, and restore steps.
  * **Zero Division Protection**: Generates `DivisionByZeroException`, captured in CSRs.
* **Bit operations**: `clz rd, rs1` counts leading zeros (32 for zero); `popcnt rd, rs1` counts set bits using a parallel Hamming-weight algorithm. These instructions are implemented in the Python ISA, assembler, and ALU.
* **Pipeline timing**: The Python 4-stage and 6-stage pipelines use the ALU latency to model stalls for multi-cycle `mul`, `div`, and `mod` operations.
* **Condition Codes**: Sets `Z` (Zero), `N` (Negative), `C` (Carry/Borrow), `V` (Signed Overflow).

---

## Software Suite & Toolchain

The framework provides a modular set of tools:
* `risc201/core/isa.py`: Instruction encodings, bit manipulation, register aliases.
* `risc201/alu/alu.py`: Optimized ALU with configurable multiplier and divider algorithms.
* `risc201/core/registers.py`: General Purpose Registers with hardwired `r0`, and CSR registers (`EPC`, `CAUSE`, `STATUS`, `BADVADDR`).
* `risc201/core/memory.py`: Byte-addressable 64 KB memory with alignment and boundary protection.
* `risc201/core/stack.py`: Stack preprocessor expanding `push`, `pop`, `enter`, `leave`, and leaf function optimization (`enter_leaf`, `leave_leaf`) with canary verification.
* `risc201/ui/visualizer.py`: ASCII Stack Memory Visualizer & Pipeline State renderer.
* `risc201/core/pmc.py`: Hardware Performance Monitoring Counters.
* `risc201/pipelines/branch_predictor.py`: 2-bit Saturating Counter Predictor + BTB.
* `risc201/pipelines/forwarding.py`: Forwarding Unit and Load-Use Hazard Detection Unit.
* `risc201/pipelines/pipeline_4stage.py`: Cycle-accurate 4-stage pipeline processor.
* `risc201/pipelines/pipeline_6stage.py`: Cycle-accurate 6-stage pipeline processor.
* `risc201/control/microcode.py`: Microprogrammed CPU with Horizontal and Vertical control stores.
* `risc201/toolchain/assembler.py`: Two-pass assembler emitting binary words and hex listings.
* `risc201/toolchain/disassembler.py`: Machine code disassembler.
* `risc201/ui/debugger.py`: Interactive CLI debugger REPL.
* `cli.py`: Unified Python command line runner.
* `benchmarks/benchmark.py`: Complete comparative benchmark suite in Python.
* `tests/test_all.py`: Unit test runner in Python.

## Running the Python Project

No compilation is required. From the repository root:

```powershell
py cli.py run programs/02_factorial.asm --arch 4stage
py cli.py run programs/02_factorial.asm --arch 6stage
py -m unittest discover -s tests
py benchmarks/benchmark.py
```

On systems where Python is invoked as `python3`, replace `py` with `python3`. The `Makefile` provides `make test` and `make benchmark` for environments with Make installed.

---

## CLI & Debugger Usage Guide

### 1. Assemble an Assembly Program
```bash
python3 cli.py assemble programs/01_basic_test.asm -o out.hex
```

### 2. Disassemble Machine Code
```bash
# Disassemble a single 32-bit hex word
python3 cli.py disassemble 0x7C780000

# Disassemble a hex file
python3 cli.py disassemble out.hex
```

### 3. Run Simulation
```bash
# Run on 4-stage pipeline
python3 cli.py run programs/02_factorial.asm --arch 4stage

# Run on 6-stage pipeline
python3 cli.py run programs/02_factorial.asm --arch 6stage

# Run on Microprogrammed CPU (Vertical model)
python3 cli.py run programs/01_basic_test.asm --arch micro --vertical

# Run with customized register inputs (e.g. r1=10, r2=20)
python3 cli.py run programs/01_basic_test.asm --set-reg "r1=10,r2=20"

# Run with customized memory words (e.g. at 0x1000 and 0x1004)
python3 cli.py run programs/07_vector_dot.asm --set-mem "0x1000=42,0x1004=99"
```

### 4. Interactive CLI Debugger
```bash
python3 cli.py debug programs/02_factorial.asm --arch 4stage
```
**Interactive Debugger Commands:**
* `s`, `step [n]`: Step by $n$ clock cycles.
* `c`, `run`: Continue execution until breakpoint or halt.
* `b`, `break <addr | label>`: Set breakpoint at address or label.
* `d`, `delete <addr>`: Delete breakpoint.
* `r`, `regs`: Display general registers and CSR state.
* `stack`, `st`: Render the Active ASCII Stack Frame.
* `pipe`, `p`: Render the pipeline stages and instructions in flight.
* `pmc`, `stats`: Display performance monitoring counters (CPI, stalls, branches).
* `m`, `mem <addr> [n]`: Dump $n$ words of memory.
* `disasm [n]`: Disassemble instructions near the current PC.
* `reset`: Reset CPU to initial state.
* `q`, `quit`: Exit debugger.

---

## Empirical Benchmarks & Experimental Results

The following results were recorded by running `python3 benchmarks/benchmark.py`. Rerun them with the current configuration before comparing performance:

### 1. 4-Stage vs. 6-Stage Pipeline Comparison
| Benchmark Program | Architecture | Cycles | Instructions | Stalls | CPI | IPC |
|---|---|---|---|---|---|---|
| `01_basic_test.asm` | 4-Stage | 31 | 27 | 0 | **1.148** | 0.871 |
| `01_basic_test.asm` | 6-Stage | 35 | 27 | 0 | **1.296** | 0.771 |
| `02_factorial.asm` (n=5) | 4-Stage | 178 | 156 | 10 | **1.141** | 0.876 |
| `02_factorial.asm` (n=5) | 6-Stage | 198 | 156 | 10 | **1.269** | 0.788 |
| `05_hazard_bench.asm` | 4-Stage | 21 | 16 | 2 | **1.312** | 0.762 |
| `05_hazard_bench.asm` | 6-Stage | 23 | 16 | 2 | **1.438** | 0.696 |
| `06_branch_bench.asm` | 4-Stage | 909 | 883 | 0 | **1.029** | 0.971 |
| `06_branch_bench.asm` | 6-Stage | 957 | 883 | 0 | **1.084** | 0.923 |

### 2. Forwarding Network Impact (`05_hazard_bench.asm`)
| Architecture | Forwarding Network | Total Cycles | Stall Cycles | CPI | Forwarding Events |
|---|---|---|---|---|---|
| **4-Stage** | **ENABLED** | **21** | **2** | **1.312** | 21 |
| 4-Stage | DISABLED | 41 | 42 | 2.562 | 0 |
| **6-Stage** | **ENABLED** | **23** | **2** | **1.438** | 12 |
| 6-Stage | DISABLED | 43 | 42 | 2.688 | 0 |

> **Key Takeaway**: The Full-Matrix Forwarding Network eliminates over **95% of data hazard stalls**, delivering a **1.95x speedup** on dependency-heavy workloads.

### 3. Dynamic 2-bit BTB Predictor vs. Static Predictors (`06_branch_bench.asm`)
| Architecture | Predictor Mode | Total Cycles | Branches Evaluated | Mispredictions | Mispredict Rate | CPI |
|---|---|---|---|---|---|---|
| **4-Stage** | **Dynamic 2-Bit + BTB** | **909** | 220 | **23** | **10.5%** | **1.029** |
| 4-Stage | Static Always Not-Taken | 1085 | 220 | 199 | 90.5% | 1.229 |
| **6-Stage** | **Dynamic 2-Bit + BTB** | **957** | 220 | **23** | **10.5%** | **1.084** |
| 6-Stage | Static Always Not-Taken | 1485 | 220 | 199 | 90.5% | 1.682 |

> **Key Takeaway**: In the 6-stage pipeline where branch resolution incurs a 3-cycle penalty, the Dynamic 2-bit BTB predictor reduces execution time from 1,485 cycles to 957 cycles (**35.6% cycle reduction**).

### 4. Microprogrammed Control Store Comparison
| Attribute | Horizontal Model | Vertical Model |
|---|---|---|
| Microinstruction Width | 28 bits | **14 bits** |
| Control Store ROM Capacity | 2,296 bits | **1,148 bits (50% reduction)** |
| Decoding Overhead | Zero (direct lines) | Requires micro-decoders |
| Micro-Cycles Per Instruction | 3.45 | 3.45 |

### 5. Security Canary & Exception Trapping (`04_buffer_overflow.asm`)
* **Test Outcome**: Buffer overflow into stack canary successfully intercepted!
* **Captured Exception**: `TRAP triggered with code 6` (`STACK_CANARY_CORRUPTED`).
* **Faulting PC captured in `EPC`**: `0x0000004C`.
* **CSR Status**: `0x05` (`EX=1 Mode=User IE=1`).

### 6. Leaf Function Optimization Impact (`08_leaf_bench.asm`)
| Subroutine Convention | Total Cycles | Instructions Committed | CPI | Stack Memory Operations |
|---|---|---|---|---|
| **Standard Frame (RA + FP + Canary)** | 287 | 257 | 1.117 | 6 per call (60 total) |
| **Leaf-Optimized (`enter_leaf` / `leave_leaf`)** | **120** | **100** | **1.200** | **0 per call (0 total)** |

> **Key Takeaway**: Leaf Function Optimization delivers a **2.39x execution speedup** (58.2% cycle reduction) and completely eliminates stack memory bus traffic by avoiding saving the return address and frame pointer when safe.

---

## Running Verification Tests
Execute the comprehensive test runner to verify all subsystems:
```bash
python3 tests/test_all.py
```
Expected output:
```
...............
----------------------------------------------------------------------
Ran 15 tests in 0.192s

OK
```
