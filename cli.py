#!/usr/bin/env python3
"""
RISC201 Unified Command Line Interface
Usage:
  python3 cli.py assemble <file.asm> [-o out.hex]
  python3 cli.py disassemble <file.hex | hex_word>
  python3 cli.py run <file.asm> [--arch 4stage|6stage|micro] [--no-forwarding] [--branch static_not_taken|dynamic_2bit]
  python3 cli.py debug <file.asm> [--arch 4stage|6stage|micro]
  python3 cli.py benchmark
"""

import sys
import argparse
from typing import Optional
# Windows consoles default to cp1252 and crash on box-drawing/emoji characters.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from risc201.toolchain.assembler import Assembler, AssembledProgram
from risc201.toolchain.disassembler import Disassembler
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.pipelines.pipeline_6stage import Processor6Stage
from risc201.control.microcode import MicroprogrammedCPU
from risc201.core.memory import Memory
from risc201.ui.debugger import CLIDebugger
from risc201.pipelines.branch_predictor import PredictorMode

def load_and_assemble(filepath: str) -> AssembledProgram:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
    except IOError as e:
        print(f"[Error] Failed to read source file '{filepath}': {e}")
        sys.exit(1)

    assembler = Assembler()
    try:
        prog = assembler.assemble(src)
    except Exception as e:
        print(f"[Assembler Error] {e}")
        sys.exit(1)
    return prog


def cmd_assemble(args):
    prog = load_and_assemble(args.file)
    hex_lines = prog.to_hex_lines()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(hex_lines) + "\n")
        print(f"[*] Assembled {len(prog.text_words)} instructions to '{args.output}'.")
    else:
        print("=== RISC201 Machine Listing ===")
        for line in hex_lines:
            print(line)
        print(f"\nTotal Instructions: {len(prog.text_words)}")
        if prog.data_bytes:
            print(f"Total Initialized Data: {len(prog.data_bytes)} bytes")


def cmd_disassemble(args):
    target = args.input.strip()
    if target.endswith(".hex") or target.endswith(".txt"):
        try:
            with open(target, "r") as f:
                lines = f.readlines()
            for line in lines:
                parts = line.split(":")
                if len(parts) >= 2:
                    word_part = parts[1].split(";")[0].strip()
                    word = int(word_part, 16)
                    pc = int(parts[0].strip(), 16)
                    print(f"0x{pc:08X}: {Disassembler.disassemble_word(word, pc)}")
        except Exception as e:
            print(f"[Disassembly Error] {e}")
    else:
        # Direct hex or binary word input
        if target.startswith("0x") or target.startswith("0X"):
            val = int(target, 16)
            print(f"{target} --> {Disassembler.disassemble_word(val)}")
        elif all(c in "01 " for c in target) and len(target.replace(" ", "")) == 32:
            print(f"Binary --> {Disassembler.disassemble_binary(target)}")
        else:
            try:
                val = int(target, 16)
                print(f"0x{val:08X} --> {Disassembler.disassemble_word(val)}")
            except ValueError:
                print(f"[Error] Invalid machine code format: '{target}'")


def build_cpu(arch: str, prog: AssembledProgram, enable_forwarding: bool, branch_mode: str, vertical_micro: bool):
    mem = Memory()
    mem.load_words(prog.text_start_addr, prog.text_words)
    if prog.data_bytes:
        mem.load_bytes(prog.data_start_addr, bytes(prog.data_bytes))

    b_mode = PredictorMode(branch_mode)

    if arch == "4stage":
        return Processor4Stage(
            memory=mem,
            enable_forwarding=enable_forwarding,
            branch_mode=b_mode
        )
    elif arch == "6stage":
        return Processor6Stage(
            memory=mem,
            enable_forwarding=enable_forwarding,
            branch_mode=b_mode
        )
    elif arch == "micro":
        return MicroprogrammedCPU(
            memory=mem,
            use_vertical=vertical_micro
        )
    else:
        raise ValueError(f"Unknown architecture: {arch}")


def cmd_run(args):
    prog = load_and_assemble(args.file)
    enable_forwarding = not args.no_forwarding
    cpu = build_cpu(args.arch, prog, enable_forwarding, args.branch, args.vertical)

    # Apply custom register inputs
    if getattr(args, "set_reg", None):
        for item in args.set_reg.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                reg_name = k.strip().lower()
                reg_id = int(reg_name.replace("r", "").replace("fp", "13").replace("sp", "14").replace("ra", "15"))
                val = int(v.strip(), 0)
                cpu.rf.write(reg_id, val)
                print(f"[*] Custom Input: Initialized r{reg_id} = {val} (0x{val & 0xFFFFFFFF:08X})")

    # Apply custom memory inputs
    if getattr(args, "set_mem", None):
        for item in args.set_mem.split(","):
            if "=" in item:
                addr_str, val_str = item.split("=", 1)
                addr = int(addr_str.strip(), 0)
                val = int(val_str.strip(), 0)
                cpu.memory.write_word(addr, val)
                print(f"[*] Custom Input: Initialized mem[0x{addr:08X}] = {val} (0x{val & 0xFFFFFFFF:08X})")

    print(f"[*] Running '{args.file}' on RISC201 [{args.arch.upper()}]...")
    cpu.run()

    if cpu.exception_raised and cpu.last_exception:
        print(f"\n[🚨 CPU EXCEPTION ENCOUNTERED]")
        print(f"  {cpu.last_exception}")
        print(f"  CSRs: {cpu.csr.to_dict()}")
    else:
        print(f"[*] Execution finished successfully (Halted).")

    # Display final architectural register file state
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                  FINAL REGISTER FILE VALUES                  ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    for row in range(0, 16, 4):
        items = []
        for reg_id in range(row, row + 4):
            val = cpu.rf.read(reg_id)
            name = f"r{reg_id}"
            if reg_id == 13: name = "fp(r13)"
            elif reg_id == 14: name = "sp(r14)"
            elif reg_id == 15: name = "ra(r15)"
            items.append(f"{name:>7}: {val:<6} (0x{val & 0xFFFFFFFF:08X})")
        print("║  " + "  ".join(items) + "  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    print("\n" + cpu.pmc.format_summary())


def cmd_debug(args):
    prog = load_and_assemble(args.file)
    enable_forwarding = not args.no_forwarding
    cpu = build_cpu(args.arch, prog, enable_forwarding, args.branch, args.vertical)

    # Apply custom register inputs
    if getattr(args, "set_reg", None):
        for item in args.set_reg.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                reg_name = k.strip().lower()
                reg_id = int(reg_name.replace("r", "").replace("fp", "13").replace("sp", "14").replace("ra", "15"))
                val = int(v.strip(), 0)
                cpu.rf.write(reg_id, val)
                print(f"[*] Custom Input: Initialized r{reg_id} = {val} (0x{val & 0xFFFFFFFF:08X})")

    # Apply custom memory inputs
    if getattr(args, "set_mem", None):
        for item in args.set_mem.split(","):
            if "=" in item:
                addr_str, val_str = item.split("=", 1)
                addr = int(addr_str.strip(), 0)
                val = int(val_str.strip(), 0)
                cpu.memory.write_word(addr, val)
                print(f"[*] Custom Input: Initialized mem[0x{addr:08X}] = {val} (0x{val & 0xFFFFFFFF:08X})")

    debugger = CLIDebugger(cpu, prog, is_micro=(args.arch == "micro"))
    debugger.run_repl()


def cmd_benchmark(args):
    import benchmark
    benchmark.run_all_benchmarks()


def main():
    parser = argparse.ArgumentParser(description="RISC201 Processor Simulation & Toolchain Suite")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # assemble
    p_asm = subparsers.add_parser("assemble", help="Assemble RISC201 assembly to machine code")
    p_asm.add_argument("file", help="Path to .asm file")
    p_asm.add_argument("-o", "--output", help="Output .hex file")

    # disassemble
    p_dis = subparsers.add_parser("disassemble", help="Disassemble machine code hex/binary words")
    p_dis.add_argument("input", help="Hex file path, or 32-bit hex word e.g. 0x08400005, or 32-bit binary")

    # run
    p_run = subparsers.add_parser("run", help="Simulate execution of program")
    p_run.add_argument("file", help="Path to .asm file")
    p_run.add_argument("--arch", choices=["4stage", "6stage", "micro"], default="4stage", help="Processor architecture model")
    p_run.add_argument("--no-forwarding", action="store_true", help="Disable data forwarding network")
    p_run.add_argument("--branch", choices=["static_not_taken", "static_taken", "dynamic_2bit"], default="dynamic_2bit", help="Branch prediction mode")
    p_run.add_argument("--vertical", action="store_true", help="Use vertical microprogramming model for micro architecture")
    p_run.add_argument("--set-reg", help="Set initial register values before execution, e.g. 'r1=10,r2=20'")
    p_run.add_argument("--set-mem", help="Set initial memory words before execution, e.g. '0x1000=42,0x1004=99'")

    # debug
    p_dbg = subparsers.add_parser("debug", help="Launch interactive CLI debugger")
    p_dbg.add_argument("file", help="Path to .asm file")
    p_dbg.add_argument("--arch", choices=["4stage", "6stage", "micro"], default="4stage", help="Processor architecture model")
    p_dbg.add_argument("--no-forwarding", action="store_true", help="Disable data forwarding")
    p_dbg.add_argument("--branch", choices=["static_not_taken", "static_taken", "dynamic_2bit"], default="dynamic_2bit")
    p_dbg.add_argument("--vertical", action="store_true")
    p_dbg.add_argument("--set-reg", help="Set initial register values before debugging, e.g. 'r1=10,r2=20'")
    p_dbg.add_argument("--set-mem", help="Set initial memory words before debugging, e.g. '0x1000=42'")

    # benchmark
    subparsers.add_parser("benchmark", help="Run comparative benchmark evaluation across all processor models")

    args = parser.parse_args()
    if args.command == "assemble":
        cmd_assemble(args)
    elif args.command == "disassemble":
        cmd_disassemble(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "debug":
        cmd_debug(args)
    elif args.command == "benchmark":
        cmd_benchmark(args)

if __name__ == "__main__":
    main()
