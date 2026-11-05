"""
RISC201 Register File & Control and Status Registers (CSRs)
Implements:
1. Hardwired Zero Register (r0): Always returns 0, ignores writes.
2. 16 General Purpose Registers (r0..r15) with standard aliases.
3. Protected Control and Status Registers (EPC, CAUSE, STATUS, BADVADDR)
   and hardware exception handling framework.
"""

from enum import IntEnum
from typing import Dict, List, Optional
from risc201.core.isa import to_signed32, to_unsigned32, REGISTER_NAMES, REGISTER_ALIASES

class CSRCause(IntEnum):
    NONE                    = 0x00
    DIVISION_BY_ZERO        = 0x01
    ILLEGAL_INSTRUCTION     = 0x02
    MISALIGNED_ACCESS       = 0x03
    STACK_OVERFLOW          = 0x04
    STACK_UNDERFLOW         = 0x05
    STACK_CANARY_CORRUPTED  = 0x06
    OUT_OF_BOUNDS           = 0x07
    BREAKPOINT              = 0x08
    TRAP_CALL               = 0x09

CSR_CAUSE_NAMES: Dict[int, str] = {
    CSRCause.NONE: "None",
    CSRCause.DIVISION_BY_ZERO: "Division By Zero",
    CSRCause.ILLEGAL_INSTRUCTION: "Illegal Instruction",
    CSRCause.MISALIGNED_ACCESS: "Misaligned Memory Access",
    CSRCause.STACK_OVERFLOW: "Stack Overflow Exception",
    CSRCause.STACK_UNDERFLOW: "Stack Underflow Exception",
    CSRCause.STACK_CANARY_CORRUPTED: "Security Trap: Stack Canary Corrupted!",
    CSRCause.OUT_OF_BOUNDS: "Out of Bounds Memory Reference",
    CSRCause.BREAKPOINT: "Breakpoint Trap",
    CSRCause.TRAP_CALL: "Software Trap",
}

class CPUException(Exception):
    """Architectural CPU exception captured by CSRs."""
    def __init__(self, cause: CSRCause, pc: int, message: str, badvaddr: Optional[int] = None):
        super().__init__(message)
        self.cause = cause
        self.pc = pc
        self.message = message
        self.badvaddr = badvaddr if badvaddr is not None else pc

    def __str__(self) -> str:
        addr_str = f" [BadAddr: 0x{self.badvaddr:08X}]" if self.badvaddr is not None else ""
        return f"CPUException({CSR_CAUSE_NAMES.get(self.cause, 'Unknown')}) at PC=0x{self.pc:08X}: {self.message}{addr_str}"


class CSRFile:
    """
    Control and Status Registers (CSRs):
    - EPC (Exception Program Counter): PC where exception occurred.
    - CAUSE: Architectural cause code.
    - STATUS: Bit 0 = IE (Interrupt Enable), Bit 1 = Mode (0=User, 1=Kernel), Bit 2 = EX (Exception Active).
    - BADVADDR: Bad Virtual Address of memory fault.
    """
    def __init__(self):
        self.epc: int = 0
        self.cause: CSRCause = CSRCause.NONE
        self.status: int = 0x01  # IE=1 by default
        self.badvaddr: int = 0

    def trigger_exception(self, cause: CSRCause, faulting_pc: int, badvaddr: Optional[int] = None):
        """Records an architectural exception into CSRs."""
        self.epc = to_unsigned32(faulting_pc)
        self.cause = cause
        self.status = (self.status | 0x04)  # Set EX bit (bit 2)
        self.badvaddr = to_unsigned32(badvaddr if badvaddr is not None else faulting_pc)

    def clear_exception(self):
        self.cause = CSRCause.NONE
        self.status = (self.status & ~0x04)  # Clear EX bit

    def to_dict(self) -> Dict[str, str]:
        return {
            "EPC": f"0x{self.epc:08X}",
            "CAUSE": f"{self.cause.value} ({CSR_CAUSE_NAMES.get(self.cause, 'Unknown')})",
            "STATUS": f"0x{self.status:02X} (EX={int(bool(self.status & 4))} Mode={'Kernel' if self.status & 2 else 'User'} IE={int(bool(self.status & 1))})",
            "BADVADDR": f"0x{self.badvaddr:08X}",
        }


class RegisterFile:
    """
    16-register General Purpose Register File with:
    - Modification 1: Hardwired Zero Register (r0)
    - Full descending stack pointers (r13=fp, r14=sp, r15=ra)
    - Modification tracking for visual debugger
    """
    NUM_REGS = 16

    def __init__(self):
        self.regs: List[int] = [0] * self.NUM_REGS
        self.last_written_reg: Optional[int] = None
        self.modified_mask: int = 0

    def reset(self, initial_sp: int = 0x00004000):
        self.regs = [0] * self.NUM_REGS
        self.regs[14] = initial_sp  # Default sp
        self.regs[13] = initial_sp  # Default fp
        self.last_written_reg = None
        self.modified_mask = 0

    def read(self, reg_idx: int) -> int:
        """
        Read from register.
        Hardwired r0: ALWAYS returns 0.
        """
        if reg_idx == 0:
            return 0
        if 0 <= reg_idx < self.NUM_REGS:
            return self.regs[reg_idx]
        raise IndexError(f"Register index out of range: {reg_idx}")

    def write(self, reg_idx: int, value: int):
        """
        Write to register.
        Hardwired r0: Discard write attempt.
        """
        if reg_idx == 0:
            # Silently discard write to hardwired zero register r0
            return
        if 0 <= reg_idx < self.NUM_REGS:
            self.regs[reg_idx] = to_signed32(value)
            self.last_written_reg = reg_idx
            self.modified_mask |= (1 << reg_idx)
        else:
            raise IndexError(f"Register index out of range: {reg_idx}")

    def clear_modified_flags(self):
        self.modified_mask = 0
        self.last_written_reg = None

    def read_by_name(self, name: str) -> int:
        idx = REGISTER_ALIASES.get(name.lower())
        if idx is None:
            raise KeyError(f"Unknown register alias '{name}'")
        return self.read(idx)

    def write_by_name(self, name: str, value: int):
        idx = REGISTER_ALIASES.get(name.lower())
        if idx is None:
            raise KeyError(f"Unknown register alias '{name}'")
        self.write(idx, value)

    @property
    def sp(self) -> int:
        return self.read(14)

    @sp.setter
    def sp(self, value: int):
        self.write(14, value)

    @property
    def fp(self) -> int:
        return self.read(13)

    @fp.setter
    def fp(self, value: int):
        self.write(13, value)

    @property
    def ra(self) -> int:
        return self.read(15)

    @ra.setter
    def ra(self, value: int):
        self.write(15, value)

    def dump(self) -> Dict[str, int]:
        return {f"r{i}": self.regs[i] for i in range(self.NUM_REGS)}
