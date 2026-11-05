"""
RISC201 Memory Subsystem
Features:
- Byte-addressable, 32-bit word-aligned memory.
- Memory map: Text (Code), Data/Heap, Red Zone Guard Page, Stack.
- Misaligned memory access detection.
- Stack boundary verification (Overflow, Underflow, Red Zone guard violation).
"""

from typing import Dict, List, Optional
from risc201.core.isa import to_signed32, to_unsigned32
from risc201.core.registers import CSRCause, CPUException

class Memory:
    """
    32-bit Memory subsystem with architectural boundary protection.
    Default Memory Layout:
      0x00000000 - 0x00000FFF : Text Segment (Instructions) [4 KB]
      0x00001000 - 0x00002BFF : Data & Heap Segment [7 KB]
      0x00002C00 - 0x00002FFF : Stack Red Zone / Guard Page [1 KB]
      0x00003000 - 0x00004000 : Full-Descending Stack Segment [4 KB] (sp starts at 0x4000)
    """
    DEFAULT_SIZE = 0x00010000  # 64 KB total space
    DEFAULT_STACK_BASE = 0x00004000
    DEFAULT_STACK_LIMIT = 0x00003000
    DEFAULT_REDZONE_BASE = 0x00002C00
    DEFAULT_REDZONE_LIMIT = 0x00003000

    def __init__(
        self,
        size: int = DEFAULT_SIZE,
        stack_base: int = DEFAULT_STACK_BASE,
        stack_limit: int = DEFAULT_STACK_LIMIT,
        redzone_base: int = DEFAULT_REDZONE_BASE,
        redzone_limit: int = DEFAULT_REDZONE_LIMIT
    ):
        self.size = size
        self.stack_base = stack_base
        self.stack_limit = stack_limit
        self.redzone_base = redzone_base
        self.redzone_limit = redzone_limit

        self.bytes = bytearray(size)
        self.last_written_addr: Optional[int] = None
        self.write_history: Dict[int, int] = {}

    def reset(self):
        self.bytes = bytearray(self.size)
        self.last_written_addr = None
        self.write_history.clear()

    def check_alignment(self, addr: int, pc: int = 0):
        if addr % 4 != 0:
            raise CPUException(
                cause=CSRCause.MISALIGNED_ACCESS,
                pc=pc,
                message=f"Misaligned 32-bit word access at address 0x{addr:08X} (must be 4-byte aligned)",
                badvaddr=addr
            )

    def check_bounds(self, addr: int, pc: int = 0):
        if addr < 0 or addr + 3 >= self.size:
            raise CPUException(
                cause=CSRCause.OUT_OF_BOUNDS,
                pc=pc,
                message=f"Memory access out of bounds: 0x{addr:08X} (valid range: 0x00000000 - 0x{self.size-1:08X})",
                badvaddr=addr
            )

    def check_stack_safety(self, current_sp: int, pc: int = 0):
        """Verifies full-descending stack bounds against underflow and overflow."""
        if current_sp > self.stack_base:
            raise CPUException(
                cause=CSRCause.STACK_UNDERFLOW,
                pc=pc,
                message=f"Stack underflow detected: SP=0x{current_sp:08X} exceeds stack base 0x{self.stack_base:08X}",
                badvaddr=current_sp
            )
        if current_sp < self.stack_limit:
            raise CPUException(
                cause=CSRCause.STACK_OVERFLOW,
                pc=pc,
                message=f"Stack overflow detected: SP=0x{current_sp:08X} penetrated below stack limit 0x{self.stack_limit:08X}",
                badvaddr=current_sp
            )

    def read_word(self, addr: int, pc: int = 0) -> int:
        """Read a 32-bit signed word from memory (Little Endian)."""
        self.check_bounds(addr, pc)
        self.check_alignment(addr, pc)

        # Read 4 bytes little endian
        b0 = self.bytes[addr]
        b1 = self.bytes[addr + 1]
        b2 = self.bytes[addr + 2]
        b3 = self.bytes[addr + 3]
        u32 = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        return to_signed32(u32)

    def write_word(self, addr: int, value: int, pc: int = 0):
        """Write a 32-bit word to memory (Little Endian)."""
        self.check_bounds(addr, pc)
        self.check_alignment(addr, pc)

        # Red zone violation check
        if self.redzone_base <= addr < self.redzone_limit:
            raise CPUException(
                cause=CSRCause.STACK_OVERFLOW,
                pc=pc,
                message=f"Security violation: Attempted write into Stack Red Zone / Guard Page at 0x{addr:08X}",
                badvaddr=addr
            )

        u32 = to_unsigned32(value)
        self.bytes[addr] = u32 & 0xFF
        self.bytes[addr + 1] = (u32 >> 8) & 0xFF
        self.bytes[addr + 2] = (u32 >> 16) & 0xFF
        self.bytes[addr + 3] = (u32 >> 24) & 0xFF

        self.last_written_addr = addr
        self.write_history[addr] = to_signed32(u32)

    def load_words(self, start_addr: int, words: List[int]):
        """Bulk load a list of 32-bit words starting at given address."""
        for i, word in enumerate(words):
            addr = start_addr + (i * 4)
            self.write_word(addr, word)

    def load_bytes(self, start_addr: int, raw_data: bytes):
        """Load raw byte string into memory."""
        self.check_bounds(start_addr)
        self.check_bounds(start_addr + len(raw_data) - 1)
        self.bytes[start_addr : start_addr + len(raw_data)] = raw_data
