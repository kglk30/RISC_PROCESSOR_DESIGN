"""
RISC201 Core Subsystem
Contains architectural foundations:
- isa.py: Instruction Set Architecture & bit encodings
- registers.py: General Purpose Register File (Hardwired r0) & CSRs
- memory.py: Byte-addressable 64 KB memory & boundary protection
- stack.py: Full-descending stack preprocessor & canary verification
- pmc.py: Hardware Performance Monitoring Counters
"""

from risc201.core.isa import Opcode, DecodedInstruction, decode_instruction, encode_instruction
from risc201.core.registers import RegisterFile, CSRFile, CSRCause, CPUException
from risc201.core.memory import Memory
from risc201.core.stack import StackPreprocessor, CANARY_MAGIC
from risc201.core.pmc import PMC
