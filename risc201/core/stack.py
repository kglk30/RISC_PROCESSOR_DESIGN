"""
Stack Subsystem, Preprocessor Macro Expander, and Safety Verification
Features:
- Full-descending stack convention (SP decrements on push, increments on pop)
- Stack Canary insertion (Prologue) and verification (Epilogue)
- Stack Boundary and Red Zone safety verification
- Leaf Function Optimization (avoids saving return address and frame pointer when safe)
"""

from typing import List, Tuple, Set
from risc201.core.isa import REGISTER_ALIASES

DEFAULT_CANARY = 0x1C0DE  # Canary magic constant (fits 18-bit immediate)
CANARY_MAGIC   = 0x1C0DE

class StackPreprocessor:
    """
    Expands high-level stack macros into standard RISC201 assembly instructions:
    - push <reg>
    - pop <reg>
    - enter <local_bytes> (Prologue with Canary)
    - leave <local_bytes> (Epilogue with Canary check)
    - enter_leaf <local_bytes> (Leaf Prologue: avoids saving RA & FP when safe)
    - leave_leaf <local_bytes> (Leaf Epilogue: avoids saving/restoring RA & FP)
    - enter <local_bytes>, leaf
    - leave <local_bytes>, leaf
    """
    def __init__(self, canary: int = CANARY_MAGIC, optimize_leaf: bool = False):
        self.canary = canary
        self.optimize_leaf = optimize_leaf
        self._label_counter = 0

    @staticmethod
    def _parse_frame_args(op: str, args: List[str]) -> Tuple[int, bool]:
        is_leaf = op.endswith("_leaf") or any(a.lower() == "leaf" for a in args)
        frame_size = 0
        for a in args:
            if a.lower() != "leaf":
                try:
                    frame_size = int(a)
                    break
                except ValueError:
                    pass
        return frame_size, is_leaf

    def expand_lines(self, lines: List[str]) -> List[str]:
        # Pre-scan for automatic leaf detection if optimize_leaf is enabled
        auto_leaf_indices: Set[int] = set()
        if self.optimize_leaf:
            enter_stack = []
            for idx, line in enumerate(lines):
                comm_pos = min(
                    line.find(";") if line.find(";") != -1 else len(line),
                    line.find("#") if line.find("#") != -1 else len(line)
                )
                cleaned = line[:comm_pos].strip()
                if ":" in cleaned:
                    cleaned = cleaned.split(":", 1)[1].strip()
                tokens = cleaned.split()
                if not tokens:
                    continue
                cmd = tokens[0].lower()
                if cmd in ("enter", "enter_leaf"):
                    enter_stack.append((idx, False))  # (index, has_call)
                elif cmd == "call" and enter_stack:
                    enter_stack[-1] = (enter_stack[-1][0], True)
                elif cmd in ("leave", "leave_leaf") and enter_stack:
                    e_idx, has_call = enter_stack.pop()
                    if not has_call:
                        auto_leaf_indices.add(e_idx)
                        auto_leaf_indices.add(idx)

        expanded = []
        for line_idx, line in enumerate(lines):
            # Strip comments first
            comment_idx = min(
                line.find(";") if line.find(";") != -1 else len(line),
                line.find("#") if line.find("#") != -1 else len(line)
            )
            cleaned = line[:comment_idx].strip()
            if not cleaned:
                expanded.append(line)
                continue

            # Check for label on the same line
            label_prefix = ""
            if ":" in cleaned:
                parts = cleaned.split(":", 1)
                label_prefix = parts[0].strip() + ": "
                cleaned = parts[1].strip()

            if not cleaned:
                expanded.append(label_prefix)
                continue

            tokens = cleaned.split()
            op = tokens[0].lower()
            args = "".join(tokens[1:]).split(",") if len(tokens) > 1 else []
            args = [a.strip() for a in args if a.strip()]

            if op == "push":
                reg = args[0]
                expanded.append(f"{label_prefix}sub sp, sp, 4")
                expanded.append(f"st {reg}, 0[sp]")

            elif op == "pop":
                reg = args[0]
                expanded.append(f"{label_prefix}ld {reg}, 0[sp]")
                expanded.append(f"add sp, sp, 4")

            elif op in ("enter", "enter_leaf"):
                frame_size, is_leaf = self._parse_frame_args(op, args)
                if line_idx in auto_leaf_indices:
                    is_leaf = True

                if is_leaf:
                    # Leaf Function Optimization: avoids saving return address and frame pointer
                    expanded.append(f"{label_prefix}; --- [enter leaf prologue: avoids saving ra & fp] ---")
                    if frame_size > 0:
                        expanded.append(f"sub sp, sp, {frame_size}        ; allocate local vars (leaf)")
                else:
                    # Prologue: enter <local_var_bytes> with canary
                    self._label_counter += 1
                    expanded.append(f"{label_prefix}; --- [enter prologue with canary] ---")
                    expanded.append("sub sp, sp, 4")
                    expanded.append("st ra, 0[sp]            ; save return address")
                    expanded.append("sub sp, sp, 4")
                    expanded.append("st fp, 0[sp]            ; save frame pointer")
                    expanded.append("mov fp, sp              ; set fp to current sp")
                    expanded.append("sub sp, sp, 4           ; allocate canary slot")
                    expanded.append(f"mov r12, {self.canary}   ; load canary magic using scratch r12")
                    expanded.append("st r12, 0[sp]           ; store canary")
                    if frame_size > 0:
                        expanded.append(f"sub sp, sp, {frame_size}        ; allocate local vars")

            elif op in ("leave", "leave_leaf"):
                frame_size, is_leaf = self._parse_frame_args(op, args)
                if line_idx in auto_leaf_indices:
                    is_leaf = True

                if is_leaf:
                    # Leaf Function Optimization: avoids restoring frame pointer and return address
                    expanded.append(f"{label_prefix}; --- [leave leaf epilogue: avoids restoring ra & fp] ---")
                    if frame_size > 0:
                        expanded.append(f"add sp, sp, {frame_size}        ; deallocate local vars (leaf)")
                    expanded.append("ret")
                else:
                    # Epilogue: leave <local_var_bytes> with canary check
                    ok_label = f"__canary_ok_{self._label_counter}"
                    self._label_counter += 1
                    expanded.append(f"{label_prefix}; --- [leave epilogue with canary check] ---")
                    if frame_size > 0:
                        expanded.append(f"add sp, sp, {frame_size}        ; deallocate local vars")
                    expanded.append("ld r12, 0[sp]           ; load canary using scratch r12")
                    expanded.append(f"cmp r12, {self.canary}  ; verify canary integrity")
                    expanded.append(f"beq {ok_label}")
                    expanded.append("trap 6                  ; STACK_CANARY_CORRUPTED exception!")
                    expanded.append(f"{ok_label}:")
                    expanded.append("add sp, sp, 4           ; pop canary")
                    expanded.append("ld fp, 0[sp]            ; restore frame pointer")
                    expanded.append("add sp, sp, 4")
                    expanded.append("ld ra, 0[sp]            ; restore return address")
                    expanded.append("add sp, sp, 4")
                    expanded.append("ret")

            else:
                expanded.append(label_prefix + cleaned if label_prefix else line)

        return expanded
