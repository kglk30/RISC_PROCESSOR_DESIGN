"""
RISC201 Complete Processor Simulation Architecture
Organized into 6 separated functional subsystems:
- core       : ISA, Registers (Hardwired r0), Memory, Stack, PMC
- alu        : Optimized ALU, Booth's multiplier, Restoring divider, Flags
- pipelines  : 4-Stage & 6-Stage Processors, Forwarding Unit, Branch Predictor
- control    : Microprogrammed Control Unit (Horizontal & Vertical models)
- toolchain  : Two-pass Assembler & Disassembler
- ui         : Interactive CLI Debugger & ASCII Stack Memory Visualizer
"""

# Core
from risc201.core.isa import (
    Opcode, DecodedInstruction, decode_instruction, encode_instruction,
    to_signed32, to_unsigned32, is_branch_op, is_memory_op, is_alu_op
)
from risc201.core.registers import RegisterFile, CSRFile, CSRCause, CPUException
from risc201.core.memory import Memory
from risc201.core.stack import StackPreprocessor, CANARY_MAGIC
from risc201.core.pmc import PMC

# ALU
from risc201.alu.alu import (
    ALU, ALUFlags, MultiplierAlgorithm, DividerAlgorithm, DivisionByZeroException
)

# Pipelines
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.pipelines.pipeline_6stage import Processor6Stage
from risc201.pipelines.forwarding import HazardUnit, ForwardSource
from risc201.pipelines.branch_predictor import BranchPredictor, PredictorMode

# Control
from risc201.control.microcode import (
    MicroprogrammedCPU, ControlStore, HorizontalMicrocode, VerticalMicrocode, MicroSeqOp
)

# Toolchain
from risc201.toolchain.assembler import Assembler, AssembledProgram
from risc201.toolchain.disassembler import Disassembler

# UI
from risc201.ui.debugger import CLIDebugger
from risc201.ui.visualizer import Visualizer
