"""
Active ASCII Stack Memory Visualizer & Pipeline State Renderer
Renders:
1. Dynamic ASCII Stack Frame table sliced between SP and FP (and caller frame).
2. Pipeline Stage Status visualization showing instructions currently in flight.
"""

from typing import Optional, List, Dict
from risc201.core.memory import Memory
from risc201.core.registers import RegisterFile
from risc201.core.stack import CANARY_MAGIC
from risc201.core.isa import to_unsigned32

class Visualizer:
    """
    Renders terminal visualization for CPU debugging.
    """
    @staticmethod
    def render_stack(memory: Memory, rf: RegisterFile, max_words_above_fp: int = 4) -> str:
        """
        Renders an ASCII table showing the stack frame from SP up to FP (and above FP).
        Highlights SP, FP, canary value, saved RA, saved FP, and local variables.
        """
        sp = rf.sp
        fp = rf.fp
        stack_base = memory.stack_base

        lines = [
            "┌────────────────────────────────────────────────────────────────────────┐",
            "│                     ACTIVE ASCII STACK FRAME MAP                       │",
            "├────────────┬────────────┬─────────────┬────────────────────────────────┤",
            "│  Address   │  Hex Word  │ Signed Dec  │ Frame Annotation / Symbols     │",
            "├────────────┼────────────┼─────────────┼────────────────────────────────┤",
        ]

        # Determine range of addresses to display
        # In a full-descending stack, SP <= FP <= stack_base.
        # If SP is misaligned, align down
        aligned_sp = (sp // 4) * 4
        display_top = min(stack_base, max(fp + (max_words_above_fp * 4), aligned_sp + 32))
        display_bottom = max(memory.stack_limit, aligned_sp - 4)

        # Walk downward from high address (stack base) to low address (sp)
        for addr in range(display_top, display_bottom - 1, -4):
            val = memory.read_word(addr) if (0 <= addr + 3 < memory.size) else 0
            u32 = to_unsigned32(val)
            hex_str = f"0x{u32:08X}"
            dec_str = f"{val:>11}"

            annotations = []
            is_sp = (addr == sp)
            is_fp = (addr == fp)

            if is_sp and is_fp:
                annotations.append("--> [SP & FP]")
            elif is_sp:
                annotations.append("--> [SP] Top of Stack")
            elif is_fp:
                annotations.append("--> [FP] Current Frame Base")

            # Check for stack canary
            if val == CANARY_MAGIC:
                annotations.append("🛡️ Canary: 0x0001C0DE (Valid)")
            elif addr == fp - 4 and fp != sp:
                # Potential canary position
                annotations.append(f"⚠️ Canary slot: 0x{u32:08X} (Corrupted!)")

            # Check for saved FP
            if addr == fp:
                annotations.append(f"Saved Old FP (points to 0x{u32:08X})")
            # Check for saved RA (at fp + 4)
            elif addr == fp + 4 and addr < stack_base:
                annotations.append(f"Saved RA (ret to 0x{u32:08X})")
            elif addr > fp and addr < stack_base:
                arg_idx = (addr - fp - 4) // 4
                annotations.append(f"Caller Slot / Arg #{arg_idx}")
            elif addr < fp and addr > sp:
                var_offset = fp - addr
                annotations.append(f"Local Variable [FP - {var_offset}]")

            annot_str = " | ".join(annotations) if annotations else ""
            lines.append(f"│ 0x{addr:08X} │ {hex_str} │ {dec_str} │ {annot_str:<30} │")

        lines.append("└────────────┴────────────┴─────────────┴────────────────────────────────┘")
        lines.append(f" Stack Base: 0x{stack_base:08X}  |  SP: 0x{sp:08X}  |  FP: 0x{fp:08X}  |  Limit: 0x{memory.stack_limit:08X}")
        return "\n".join(lines)

    @staticmethod
    def render_pipeline_4stage(stages: Dict[str, str], cycle: int) -> str:
        """Renders 4-stage pipeline visualization."""
        if_s = stages.get("IF", "NOP")
        id_s = stages.get("ID/OF", "NOP")
        ex_s = stages.get("EX/MEM", "NOP")
        wb_s = stages.get("WB", "NOP")

        lines = [
            f"┌─ 4-Stage Pipeline State (Cycle {cycle}) ──────────────────────────────────┐",
            f"│ [IF    ] : {if_s:<58} │",
            f"│ [ID/OF ] : {id_s:<58} │",
            f"│ [EX/MEM] : {ex_s:<58} │",
            f"│ [WB    ] : {wb_s:<58} │",
            "└────────────────────────────────────────────────────────────────────────┘",
        ]
        return "\n".join(lines)

    @staticmethod
    def render_pipeline_6stage(stages: Dict[str, str], cycle: int) -> str:
        """Renders 6-stage pipeline visualization."""
        if_s = stages.get("IF", "NOP")
        id_s = stages.get("ID", "NOP")
        rr_s = stages.get("RR", "NOP")
        ex_s = stages.get("EX", "NOP")
        mem_s = stages.get("MEM", "NOP")
        wb_s = stages.get("WB", "NOP")

        lines = [
            f"┌─ 6-Stage Pipeline State (Cycle {cycle}) ──────────────────────────────────┐",
            f"│ [IF ] : {if_s:<62} │",
            f"│ [ID ] : {id_s:<62} │",
            f"│ [RR ] : {rr_s:<62} │",
            f"│ [EX ] : {ex_s:<62} │",
            f"│ [MEM] : {mem_s:<62} │",
            f"│ [WB ] : {wb_s:<62} │",
            "└────────────────────────────────────────────────────────────────────────┘",
        ]
        return "\n".join(lines)
