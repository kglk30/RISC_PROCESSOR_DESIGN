"""Enter RISC201 assembly directly and inspect a four-stage pipeline trace."""

import textwrap
import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from risc201.toolchain.assembler import Assembler
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.core.memory import Memory


program = None
cpu = None
history = []
source_lines = []


def in_program(address):
    return address is not None and program.text_start_addr <= address < program.text_start_addr + 4 * len(program.text_words)


def label(address):
    if not in_program(address):
        return "[bubble]"
    return program.source_map.get(address, f"0x{address:08X}").strip()


def stages():
    return (
        cpu.pc if in_program(cpu.pc) and not cpu.halted else None,
        cpu.if_id.pc if cpu.if_id.valid and in_program(cpu.if_id.pc) else None,
        cpu.id_ex.pc if cpu.id_ex.valid and in_program(cpu.id_ex.pc) else None,
        cpu.ex_wb.pc if cpu.ex_wb.valid and in_program(cpu.ex_wb.pc) else None,
    )


def show_code():
    width = 104
    print("\n+" + "-" * (width + 2) + "+")
    print(f"| {'RISC201 SOURCE CODE':<{width}} |")
    print("+" + "-" * (width + 2) + "+")
    for number, line in enumerate(source_lines, 1):
        prefix = f"{number:>3} | "
        for index, part in enumerate(textwrap.wrap(line, width - len(prefix), replace_whitespace=False, drop_whitespace=False) or [""]):
            content = (prefix if index == 0 else " " * len(prefix)) + part
            print(f"| {content:<{width}} |")
    print("+" + "-" * (width + 2) + "+")


def show_regs():
    width = 78
    print("\n+" + "-" * (width + 2) + "+")
    print(f"| {'REGISTER FILE (r0 - r15)':<{width}} |")
    print("+" + "-" * (width + 2) + "+")
    for row in range(0, 16, 4):
        cells = "  ".join(f"r{i:<2}: 0x{cpu.rf.read(i) & 0xFFFFFFFF:08X}" for i in range(row, row + 4))
        print(f"| {cells:<{width}} |")
    print("+" + "-" * (width + 2) + "+")
    print(f"| {f'PC: 0x{cpu.pc:08X}   Cycles: {cpu.pmc.cycle_count}':<{width}} |")
    print("+" + "-" * (width + 2) + "+")


def show_trace():
    if not history:
        print("No trace yet. Enter code with 'asm', then use 'run'.")
        return
    print("\n+" + "-" * 106 + "+")
    print(f"| {'RISC201 COMPLETE PIPELINE TRACE':<104} |")
    print(f"| {f'Total Clock Cycles: {len(history)}  |  Pipeline Depth: 4-Stage':<104} |")
    print("+" + "-" * 106 + "+")
    print("\n  CYCLE-BY-CYCLE STAGE STATE")
    widths = (5, 22, 22, 22, 22)
    headers = ("Cycle", "IF", "OF", "EX", "MA_RW")
    divider = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(divider)
    print("| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths)) + " |")
    print(divider)
    for n, state in enumerate(history, 1):
        cells = (str(n), *(label(address) for address in state))
        print("| " + " | ".join(f"{cell[:w]:<{w}}" for cell, w in zip(cells, widths)) + " |")
    print(divider)

    print("\n  PIPELINE SPACE-TIME TIMING DIAGRAM")
    addresses = list(dict.fromkeys(a for state in history for a in state if in_program(a)))
    stage_names = ("IF", "OF", "EX", "RW")
    for start in range(0, len(history), 10):
        chunk = history[start:start + 10]
        print(f"\n  Cycles {start + 1}-{start + len(chunk)}")
        timing_header = f"  | {'Instruction':<36} | " + " | ".join(f"C{i:<2}" for i in range(start + 1, start + len(chunk) + 1)) + " |"
        timing_border = "  +" + "-" * (len(timing_header) - 4) + "+"
        print(timing_border)
        print(timing_header)
        print(timing_border)
        for address in addresses:
            cells = []
            for state in chunk:
                cells.append(next((stage_names[i] for i, a in enumerate(state) if a == address), ""))
            if any(cells):
                title = f"0x{address:08X}: {label(address)}"
                print(f"  | {title[:36]:<36} | " + " | ".join(f"{cell:<3}" for cell in cells) + " |")
        print(timing_border)

    print("\n  FINAL REGISTER VALUES (r0 - r15)")
    print("  +----------+--------------+------------+")
    print("  | Register | Decimal      | Hex        |")
    print("  +----------+--------------+------------+")
    for reg_id in range(16):
        value = cpu.rf.read(reg_id)
        print(f"  | r{reg_id:<7} | {value:<12} | 0x{value & 0xFFFFFFFF:08X} |")
    print("  +----------+--------------+------------+")

    instructions = {line.strip().lower() for line in source_lines}
    if {"mul r3, r3, r2", "add r5, r5, r3", "st r5, 0[r9]", "ld r10, 0[r9]"} <= instructions:
        summary = (
            f"r3 holds the last factorial ({cpu.rf.read(3)}), "
            f"r5 holds the sum ({cpu.rf.read(5)}), and "
            f"r10 holds the value read back from memory ({cpu.rf.read(10)})."
        )
        print("\n" + textwrap.fill(summary, width=100))

    print(f"\nAnswer (r1): {cpu.rf.read(1)}")


def enter_code():
    global program, cpu, history, source_lines
    print("Enter RISC201 assembly, one line at a time. Type 'end' to assemble.")
    lines = []
    while True:
        try:
            line = input(f"{len(lines) + 1}> ")
        except EOFError:
            print()
            return
        if line.strip().lower() == "end":
            break
        lines.append(line)
    if not lines:
        print("No code entered.")
        return
    try:
        assembled = Assembler().assemble("\n".join(lines))
        if not assembled.text_words:
            print("No instructions assembled.")
            return
        memory = Memory()
        memory.load_words(assembled.text_start_addr, assembled.text_words)
        if assembled.data_bytes:
            memory.load_bytes(assembled.data_start_addr, bytes(assembled.data_bytes))
        new_cpu = Processor4Stage(memory=memory)
    except Exception as exc:
        print(f"Assembly error: {exc}")
        return
    program, cpu, history, source_lines = assembled, new_cpu, [], lines
    print(f"Successfully assembled and loaded {len(program.text_words)} instructions ({4 * len(program.text_words)} bytes).")
    show_code()


def run():
    global history
    if cpu is None:
        print("Enter code first with 'asm'.")
        return
    cpu.reset(initial_pc=program.text_start_addr)
    history = []
    print("Running pipeline for your custom code...")
    while not cpu.halted and len(history) < 10000:
        history.append(stages())
        cpu.step()
    if not cpu.halted:
        print("Stopped at the 10,000-cycle limit.")
    elif cpu.exception_raised:
        print(f"Execution stopped with an exception: {cpu.last_exception}")
    else:
        print(f"Execution stopped after {cpu.pmc.cycle_count} cycles.")
    show_trace()
    print("\n" + cpu.pmc.format_summary())


def main():
    print("RISC201 interactive console (4-stage)")
    print("Commands: asm/code, run, regs, trace, help, quit")
    while True:
        try:
            command = input("risc201> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if command in ("asm", "code"):
            enter_code()
        elif command in ("run", "r"):
            run()
        elif command in ("regs", "registers"):
            show_regs() if cpu is not None else print("Enter code first with 'asm'.")
        elif command == "trace":
            show_trace()
        elif command in ("help", "?"):
            print("asm/code: type instructions until 'end'; run/r: execute; regs: registers; trace: cycle table and timing diagram; quit: exit")
        elif command in ("quit", "q", "exit"):
            break
        elif command:
            print("Unknown command. Type 'help'.")


if __name__ == "__main__":
    main()
