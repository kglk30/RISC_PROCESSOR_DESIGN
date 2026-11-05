"""
Interactive CLI Debugger for RISC201
Features:
- Step-by-step execution across 4-stage, 6-stage, and Microprogrammed models
- Breakpoints by PC or symbolic label
- Active ASCII Stack Frame Visualizer
- Pipeline Stage Occupancy Display
- Register File inspection with modification highlights
- CSR inspection and exception tracking
- Hardware Performance Monitoring Counter (PMC) profiling & CPI calculations
- MicroPC state viewer
"""

import sys
from typing import Dict, Set, List, Optional, Any
from risc201.core.isa import to_unsigned32
from risc201.core.memory import Memory
from risc201.ui.visualizer import Visualizer
from risc201.toolchain.disassembler import Disassembler
from risc201.toolchain.assembler import AssembledProgram
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.pipelines.pipeline_6stage import Processor6Stage
from risc201.control.microcode import MicroprogrammedCPU

class CLIDebugger:
    """
    Interactive terminal debugger REPL.
    """
    def __init__(self, cpu: Any, program: AssembledProgram, is_micro: bool = False):
        self.cpu = cpu
        self.program = program
        self.is_micro = is_micro
        self.breakpoints: Set[int] = set()
        self.symbol_to_addr = program.symbol_table
        self.addr_to_symbol = {v: k for k, v in program.symbol_table.items()}

    def add_breakpoint(self, target: str) -> Optional[int]:
        addr = self.symbol_to_addr.get(target)
        if addr is None:
            try:
                addr = int(target, 0)
            except ValueError:
                print(f"[Debugger Error] Unknown label or invalid hex/dec address: '{target}'")
                return None
        self.breakpoints.add(addr)
        sym_name = f" ({self.addr_to_symbol[addr]})" if addr in self.addr_to_symbol else ""
        print(f"[*] Breakpoint set at 0x{addr:08X}{sym_name}")
        return addr

    def print_registers(self):
        rf = self.cpu.rf
        print("┌────────────────────────── GENERAL PURPOSE REGISTERS ──────────────────────────┐")
        for row in range(4):
            cols = []
            for col in range(4):
                idx = row * 4 + col
                name = f"r{idx}"
                if idx == 0: name = "r0(zero)"
                elif idx == 13: name = "r13(fp)"
                elif idx == 14: name = "r14(sp)"
                elif idx == 15: name = "r15(ra)"

                val = rf.read(idx)
                u32 = to_unsigned32(val)
                modified = bool(rf.modified_mask & (1 << idx))
                mod_char = "*" if modified else " "
                cols.append(f"{mod_char}{name:<9}: 0x{u32:08X}")
            print(f"│ {'  '.join(cols)} │")
        print("└───────────────────────────────────────────────────────────────────────────────┘")

        # Flags & CSRs
        flags = self.cpu.alu.flags
        print(f" Flags : {flags} | Next PC : 0x{self.cpu.pc:08X}")
        csr_dict = self.cpu.csr.to_dict()
        print(f" CSRs  : EPC={csr_dict['EPC']} | CAUSE={csr_dict['CAUSE']} | STATUS={csr_dict['STATUS']}")

    def print_pipeline(self):
        if self.is_micro:
            print(f"[Microprogrammed Control Unit] uPC = {self.cpu.upc} | Macro PC = 0x{self.cpu.pc:08X} | Halted = {self.cpu.halted}")
        elif isinstance(self.cpu, Processor4Stage):
            stages = self.cpu.get_stage_strings()
            print(Visualizer.render_pipeline_4stage(stages, self.cpu.pmc.cycle_count))
        elif isinstance(self.cpu, Processor6Stage):
            stages = self.cpu.get_stage_strings()
            print(Visualizer.render_pipeline_6stage(stages, self.cpu.pmc.cycle_count))

    def print_stack(self):
        print(Visualizer.render_stack(self.cpu.memory, self.cpu.rf))

    def print_pmc(self):
        print(self.cpu.pmc.format_summary())

    def print_disasm(self, count: int = 8):
        cur_pc = self.cpu.pc
        start_pc = max(0, cur_pc - 4)
        for i in range(count):
            addr = start_pc + (i * 4)
            if 0 <= addr + 3 < self.cpu.memory.size:
                word = self.cpu.memory.read_word(addr)
                u32 = to_unsigned32(word)
                asm = Disassembler.disassemble_word(word, addr)
                pointer = "==>" if addr == cur_pc else "   "
                sym = f"<{self.addr_to_symbol[addr]}>: " if addr in self.addr_to_symbol else ""
                print(f"{pointer} 0x{addr:08X}  {u32:08X}  {sym:<16} {asm}")

    def print_help(self):
        print("""
═════════════════════════ RISC201 DEBUGGER COMMANDS ═════════════════════════
  s, step [n]         : Step execution by 1 (or n) cycles
  sm, step_micro      : Step execution by 1 micro-cycle (Microcode CPU only)
  c, run, continue    : Continue execution until breakpoint or halt
  b, break <addr|lbl> : Set a breakpoint at address or label
  d, delete <addr>    : Remove breakpoint
  info b              : List active breakpoints
  r, regs             : Display general registers and CSR state
  stack, st           : Render Active ASCII Stack Frame
  pipe, p             : Render active instruction pipeline stages
  pmc, stats          : Display Hardware Performance Monitoring Counters (CPI/IPC)
  m, mem <addr> [n]   : Dump n memory words starting at addr
  disasm [n]          : Disassemble instructions near current PC
  reset               : Reset CPU to initial program state
  h, help, ?          : Show this help message
  q, quit             : Exit debugger
═════════════════════════════════════════════════════════════════════════════
        """)

    def step_one(self) -> bool:
        if self.cpu.halted:
            print("[*] CPU is HALTED.")
            return False

        if self.is_micro:
            cont = self.cpu.step_macro()
        else:
            cont = self.cpu.step()

        if self.cpu.exception_raised and self.cpu.last_exception:
            print(f"\n[🚨 CPU EXCEPTION TRAPPED VIA CSRs]")
            print(f" {self.cpu.last_exception}")
            print(f" CSR State: {self.cpu.csr.to_dict()}\n")

        return cont

    def run_repl(self):
        print("\n================================================================================")
        mode_str = "Microprogrammed CPU" if self.is_micro else ("4-Stage Pipeline" if isinstance(self.cpu, Processor4Stage) else "6-Stage Pipeline")
        print(f"[*] RISC201 Interactive CLI Debugger Initialized [{mode_str}]")
        print(f"[*] Type 'help' or '?' for command reference, 'step' to start.")
        print("================================================================================\n")

        self.print_pipeline()

        while True:
            try:
                prompt_pc = f"0x{self.cpu.pc:04X}"
                user_input = input(f"(risc201-dbg @ {prompt_pc})> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting debugger.")
                break

            if not user_input:
                continue

            parts = user_input.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("q", "quit", "exit"):
                print("Debugger terminated.")
                break

            elif cmd in ("h", "help", "?"):
                self.print_help()

            elif cmd in ("s", "step"):
                count = int(args[0]) if args else 1
                for _ in range(count):
                    if not self.step_one():
                        break
                self.print_pipeline()

            elif cmd in ("sm", "step_micro"):
                if self.is_micro:
                    self.cpu.step_micro()
                    print(f"[*] uPC={self.cpu.upc} | PC=0x{self.cpu.pc:08X} | IR=0x{to_unsigned32(self.cpu.ir):08X}")
                else:
                    print("[!] step_micro is only available in Microprogrammed mode.")

            elif cmd in ("c", "run", "continue"):
                print("[*] Continuing execution...")
                cycles = 0
                while not self.cpu.halted:
                    cycles += 1
                    if not self.step_one():
                        break
                    # Breakpoint hit check
                    if self.cpu.pc in self.breakpoints:
                        sym = f" ({self.addr_to_symbol[self.cpu.pc]})" if self.cpu.pc in self.addr_to_symbol else ""
                        print(f"\n[!] Hit Breakpoint at 0x{self.cpu.pc:08X}{sym} after {cycles} cycles.")
                        break
                if self.cpu.halted:
                    print(f"[*] Program execution finished. Final cycle count: {self.cpu.pmc.cycle_count}")
                self.print_pipeline()

            elif cmd in ("b", "break"):
                if args:
                    self.add_breakpoint(args[0])
                else:
                    print("Usage: break <address | label>")

            elif cmd in ("d", "delete"):
                if args:
                    addr = int(args[0], 0)
                    self.breakpoints.discard(addr)
                    print(f"[*] Deleted breakpoint at 0x{addr:08X}")
                else:
                    self.breakpoints.clear()
                    print("[*] Cleared all breakpoints.")

            elif cmd == "info" and args and args[0] == "b":
                if not self.breakpoints:
                    print("No active breakpoints.")
                else:
                    print("Active Breakpoints:")
                    for bp in sorted(self.breakpoints):
                        sym = f" ({self.addr_to_symbol[bp]})" if bp in self.addr_to_symbol else ""
                        print(f"  - 0x{bp:08X}{sym}")

            elif cmd in ("r", "regs"):
                self.print_registers()

            elif cmd in ("stack", "st"):
                self.print_stack()

            elif cmd in ("pipe", "p"):
                self.print_pipeline()

            elif cmd in ("pmc", "stats"):
                self.print_pmc()

            elif cmd in ("disasm", "dis"):
                cnt = int(args[0]) if args else 8
                self.print_disasm(cnt)

            elif cmd in ("m", "mem"):
                if not args:
                    print("Usage: mem <address> [count]")
                    continue
                start_addr = int(args[0], 0)
                cnt = int(args[1]) if len(args) > 1 else 4
                print(f"Memory Dump from 0x{start_addr:08X}:")
                for i in range(cnt):
                    addr = start_addr + (i * 4)
                    if 0 <= addr + 3 < self.cpu.memory.size:
                        w = self.cpu.memory.read_word(addr)
                        print(f"  0x{addr:08X}: 0x{to_unsigned32(w):08X} ({w:>11})")
                    else:
                        print(f"  0x{addr:08X}: [OUT OF BOUNDS]")

            elif cmd == "reset":
                self.cpu.reset()
                print("[*] CPU state reset to initial PC 0x00000000.")
                self.print_pipeline()

            else:
                print(f"[!] Unknown command '{cmd}'. Type 'help' for available commands.")
