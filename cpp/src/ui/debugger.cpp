#include "ui/debugger.hpp"
#include "ui/visualizer.hpp"
#include "toolchain/disassembler.hpp"
#include <iostream>
#include <sstream>
#include <iomanip>

namespace risc201 {

CLIDebugger::CLIDebugger(Processor4Stage* c, const AssembledProgram& prog)
    : cpu_var(c), program(prog), symbol_to_addr(prog.symbol_table), mode(0) {
    for (const auto& [k, v] : prog.symbol_table) addr_to_symbol[v] = k;
}

CLIDebugger::CLIDebugger(Processor6Stage* c, const AssembledProgram& prog)
    : cpu_var(c), program(prog), symbol_to_addr(prog.symbol_table), mode(1) {
    for (const auto& [k, v] : prog.symbol_table) addr_to_symbol[v] = k;
}

CLIDebugger::CLIDebugger(MicroprogrammedCPU* c, const AssembledProgram& prog)
    : cpu_var(c), program(prog), symbol_to_addr(prog.symbol_table), mode(2) {
    for (const auto& [k, v] : prog.symbol_table) addr_to_symbol[v] = k;
}

uint32_t CLIDebugger::get_pc() const {
    if (mode == 0) return std::get<0>(cpu_var)->pc;
    if (mode == 1) return std::get<1>(cpu_var)->pc;
    return std::get<2>(cpu_var)->pc;
}

bool CLIDebugger::is_halted() const {
    if (mode == 0) return std::get<0>(cpu_var)->halted;
    if (mode == 1) return std::get<1>(cpu_var)->halted;
    return std::get<2>(cpu_var)->halted;
}

bool CLIDebugger::has_exception() const {
    if (mode == 0) return std::get<0>(cpu_var)->exception_raised;
    if (mode == 1) return std::get<1>(cpu_var)->exception_raised;
    return std::get<2>(cpu_var)->csr.cause != CSRCause::NONE;
}

void CLIDebugger::reset_cpu() {
    if (mode == 0) std::get<0>(cpu_var)->reset();
    else if (mode == 1) std::get<1>(cpu_var)->reset();
    else std::get<2>(cpu_var)->reset();
}

void CLIDebugger::add_breakpoint(const std::string& target) {
    uint32_t addr = 0;
    auto it = symbol_to_addr.find(target);
    if (it != symbol_to_addr.end()) {
        addr = it->second;
    } else {
        try {
            addr = std::stoul(target, nullptr, 0);
        } catch (...) {
            std::cout << "[Debugger Error] Unknown label or address: '" << target << "'\n";
            return;
        }
    }
    breakpoints.insert(addr);
    std::cout << "[*] Breakpoint set at 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << addr << "\n";
}

void CLIDebugger::print_registers() {
    const RegisterFile* rf = nullptr;
    const CSRFile* csr = nullptr;
    const ALUFlags* flags = nullptr;

    if (mode == 0) {
        auto* c = std::get<0>(cpu_var);
        rf = &c->rf; csr = &c->csr; flags = &c->alu.flags;
    } else if (mode == 1) {
        auto* c = std::get<1>(cpu_var);
        rf = &c->rf; csr = &c->csr; flags = &c->alu.flags;
    } else {
        auto* c = std::get<2>(cpu_var);
        rf = &c->rf; csr = &c->csr; flags = &c->alu.flags;
    }

    std::cout << "┌────────────────────────── GENERAL PURPOSE REGISTERS ──────────────────────────┐\n";
    for (int row = 0; row < 4; ++row) {
        std::cout << "│ ";
        for (int col = 0; col < 4; ++col) {
            uint8_t idx = static_cast<uint8_t>(row * 4 + col);
            std::string name = get_register_name(idx);
            uint32_t val = static_cast<uint32_t>(rf->read(idx));
            bool modified = (rf->modified_mask & (1 << idx)) != 0;
            char mod_char = modified ? '*' : ' ';
            std::cout << mod_char << std::left << std::setw(9) << name << ": 0x"
                      << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << val << "  ";
        }
        std::cout << "│\n";
    }
    std::cout << "└───────────────────────────────────────────────────────────────────────────────┘\n";
    std::cout << " Flags : " << flags->to_string() << " | Next PC : 0x" << std::hex << std::uppercase << get_pc() << "\n";
    auto cdict = csr->to_dict();
    std::cout << " CSRs  : EPC=" << cdict["EPC"] << " | CAUSE=" << cdict["CAUSE"] << " | STATUS=" << cdict["STATUS"] << "\n";
}

void CLIDebugger::print_pipeline() {
    if (mode == 0) {
        auto* c = std::get<0>(cpu_var);
        std::cout << Visualizer::render_pipeline_4stage(c->get_stage_strings(), c->pmc.cycle_count) << "\n";
    } else if (mode == 1) {
        auto* c = std::get<1>(cpu_var);
        std::cout << Visualizer::render_pipeline_6stage(c->get_stage_strings(), c->pmc.cycle_count) << "\n";
    } else {
        auto* c = std::get<2>(cpu_var);
        std::cout << "[Microprogrammed CPU] uPC=" << std::dec << static_cast<int>(c->upc)
                  << " | PC=0x" << std::hex << std::uppercase << c->pc << " | Halted=" << (c->halted ? "true" : "false") << "\n";
    }
}

void CLIDebugger::print_stack() {
    if (mode == 0) {
        auto* c = std::get<0>(cpu_var);
        std::cout << Visualizer::render_stack(c->memory, c->rf) << "\n";
    } else if (mode == 1) {
        auto* c = std::get<1>(cpu_var);
        std::cout << Visualizer::render_stack(c->memory, c->rf) << "\n";
    } else {
        auto* c = std::get<2>(cpu_var);
        std::cout << Visualizer::render_stack(c->memory, c->rf) << "\n";
    }
}

void CLIDebugger::print_pmc() {
    if (mode == 0) std::cout << std::get<0>(cpu_var)->pmc.format_summary() << "\n";
    else if (mode == 1) std::cout << std::get<1>(cpu_var)->pmc.format_summary() << "\n";
    else std::cout << std::get<2>(cpu_var)->pmc.format_summary() << "\n";
}

void CLIDebugger::print_disasm(int count) {
    uint32_t cur = get_pc();
    uint32_t start_pc = cur > 4 ? cur - 4 : 0;
    const Memory* mem = (mode == 0) ? &std::get<0>(cpu_var)->memory :
                        (mode == 1) ? &std::get<1>(cpu_var)->memory : &std::get<2>(cpu_var)->memory;

    for (int i = 0; i < count; ++i) {
        uint32_t addr = start_pc + static_cast<uint32_t>(i * 4);
        if (addr + 3 < mem->size) {
            uint32_t w = static_cast<uint32_t>(mem->read_word(addr));
            std::string asm_str = Disassembler::disassemble_word(w, addr);
            std::string ptr = (addr == cur) ? "==>" : "   ";
            auto it = addr_to_symbol.find(addr);
            std::string sym = (it != addr_to_symbol.end()) ? "<" + it->second + ">: " : "";
            std::cout << ptr << " 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << addr
                      << "  " << std::setw(8) << w << "  " << std::left << std::setw(16) << sym << " " << asm_str << "\n";
        }
    }
}

void CLIDebugger::print_help() {
    std::cout << R"(
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
)";
}

bool CLIDebugger::step_one() {
    if (is_halted()) {
        std::cout << "[*] CPU is HALTED.\n";
        return false;
    }

    bool cont = false;
    if (mode == 0) cont = std::get<0>(cpu_var)->step();
    else if (mode == 1) cont = std::get<1>(cpu_var)->step();
    else cont = std::get<2>(cpu_var)->step_macro();

    if (has_exception()) {
        std::cout << "\n[🚨 CPU EXCEPTION TRAPPED VIA CSRs]\n";
    }
    return cont;
}

void CLIDebugger::run_repl() {
    std::cout << "\n================================================================================\n";
    std::string mstr = (mode == 0) ? "4-Stage Pipeline" : (mode == 1 ? "6-Stage Pipeline" : "Microprogrammed CPU");
    std::cout << "[*] RISC201 Interactive C++ CLI Debugger Initialized [" << mstr << "]\n";
    std::cout << "[*] Type 'help' or '?' for command reference, 'step' to start.\n";
    std::cout << "================================================================================\n\n";

    print_pipeline();

    std::string line;
    while (true) {
        std::stringstream ss_prompt;
        ss_prompt << "(risc201-dbg @ 0x" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << get_pc() << ")> ";
        std::cout << ss_prompt.str();

        if (!std::getline(std::cin, line)) break;
        std::stringstream ss(line);
        std::string cmd;
        ss >> cmd;
        if (cmd.empty()) continue;

        if (cmd == "q" || cmd == "quit" || cmd == "exit") {
            std::cout << "Debugger terminated.\n";
            break;
        } else if (cmd == "h" || cmd == "help" || cmd == "?") {
            print_help();
        } else if (cmd == "s" || cmd == "step") {
            int cnt = 1;
            ss >> cnt;
            for (int i = 0; i < cnt; ++i) {
                if (!step_one()) break;
            }
            print_pipeline();
        } else if (cmd == "sm" || cmd == "step_micro") {
            if (mode == 2) {
                std::get<2>(cpu_var)->step_micro();
                std::cout << "[*] uPC=" << std::dec << static_cast<int>(std::get<2>(cpu_var)->upc)
                          << " | PC=0x" << std::hex << std::uppercase << std::get<2>(cpu_var)->pc << "\n";
            } else {
                std::cout << "[!] step_micro is only available in Microprogrammed mode.\n";
            }
        } else if (cmd == "c" || cmd == "run" || cmd == "continue") {
            std::cout << "[*] Continuing execution...\n";
            uint64_t cycles = 0;
            while (!is_halted()) {
                cycles++;
                if (!step_one()) break;
                if (breakpoints.count(get_pc())) {
                    std::cout << "\n[!] Hit Breakpoint at 0x" << std::hex << std::uppercase << get_pc() << " after " << std::dec << cycles << " cycles.\n";
                    break;
                }
            }
            if (is_halted()) {
                std::cout << "[*] Program execution finished.\n";
            }
            print_pipeline();
        } else if (cmd == "b" || cmd == "break") {
            std::string target;
            if (ss >> target) add_breakpoint(target);
            else std::cout << "Usage: break <addr | label>\n";
        } else if (cmd == "d" || cmd == "delete") {
            std::string target;
            if (ss >> target) {
                uint32_t a = std::stoul(target, nullptr, 0);
                breakpoints.erase(a);
                std::cout << "[*] Deleted breakpoint at 0x" << std::hex << a << "\n";
            } else {
                breakpoints.clear();
                std::cout << "[*] Cleared all breakpoints.\n";
            }
        } else if (cmd == "r" || cmd == "regs") {
            print_registers();
        } else if (cmd == "stack" || cmd == "st") {
            print_stack();
        } else if (cmd == "pipe" || cmd == "p") {
            print_pipeline();
        } else if (cmd == "pmc" || cmd == "stats") {
            print_pmc();
        } else if (cmd == "disasm" || cmd == "dis") {
            int cnt = 8;
            ss >> cnt;
            print_disasm(cnt);
        } else if (cmd == "m" || cmd == "mem") {
            std::string addr_str;
            if (ss >> addr_str) {
                uint32_t addr = std::stoul(addr_str, nullptr, 0);
                int cnt = 4;
                ss >> cnt;
                const Memory* mem = (mode == 0) ? &std::get<0>(cpu_var)->memory :
                                    (mode == 1) ? &std::get<1>(cpu_var)->memory : &std::get<2>(cpu_var)->memory;
                std::cout << "Memory Dump from 0x" << std::hex << std::uppercase << addr << ":\n";
                for (int i = 0; i < cnt; ++i) {
                    uint32_t a = addr + static_cast<uint32_t>(i * 4);
                    if (a + 3 < mem->size) {
                        int32_t val = mem->read_word(a);
                        std::cout << "  0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << a
                                  << ": 0x" << std::setw(8) << static_cast<uint32_t>(val)
                                  << " (" << std::dec << val << ")\n";
                    }
                }
            } else {
                std::cout << "Usage: mem <address> [count]\n";
            }
        } else if (cmd == "reset") {
            reset_cpu();
            std::cout << "[*] CPU state reset to initial PC 0x00000000.\n";
            print_pipeline();
        } else {
            std::cout << "[!] Unknown command '" << cmd << "'. Type 'help' for available commands.\n";
        }
    }
}

} // namespace risc201
