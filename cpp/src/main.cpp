#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <string>
#include <vector>
#include <memory>
#include <algorithm>

#include "core/isa.hpp"
#include "core/registers.hpp"
#include "core/memory.hpp"
#include "core/stack.hpp"
#include "core/pmc.hpp"
#include "alu/alu.hpp"
#include "pipelines/branch_predictor.hpp"
#include "pipelines/pipeline_4stage.hpp"
#include "pipelines/pipeline_6stage.hpp"
#include "control/microcode.hpp"
#include "toolchain/assembler.hpp"
#include "toolchain/disassembler.hpp"
#include "ui/debugger.hpp"

using namespace risc201;

// Forward declare benchmark runner
extern void benchmark_pipelines();
extern void benchmark_forwarding();
extern void benchmark_branch_predictors();
extern void benchmark_microcode();
extern void benchmark_alu_algorithms();
extern void benchmark_security_canary();

static void print_usage(const char* prog_name) {
    std::cout << "RISC201 Processor Simulation & Toolchain Suite (C++17 Edition)\n"
              << "Based on Prof. Smruti R. Sarangi's 'Basic Computer Architecture' (SimpleRisc/RISC201)\n\n"
              << "Usage:\n"
              << "  " << prog_name << " assemble <file.asm> [-o out.hex]\n"
              << "  " << prog_name << " disassemble <hex_file | hex_word>\n"
              << "  " << prog_name << " run <file.asm> [--arch 4stage|6stage|micro] [--no-forwarding] [--branch mode] [--vertical]\n"
              << "  " << prog_name << " debug <file.asm> [--arch 4stage|6stage|micro] [--no-forwarding] [--branch mode] [--vertical]\n"
              << "  " << prog_name << " benchmark\n\n"
              << "Options:\n"
              << "  --arch <arch>      Processor model: 4stage (default), 6stage, or micro\n"
              << "  --no-forwarding    Disable data forwarding network (hazard stalling only)\n"
              << "  --branch <mode>    Branch predictor: dynamic_2bit (default), static_not_taken, static_taken\n"
              << "  --vertical         Use vertical microcode for microprogrammed CPU (14-bit)\n"
              << "  -o <file>          Output file for assembler\n"
              << "  -h, --help         Show this help message\n";
}

static std::string read_file(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        throw std::runtime_error("Could not open file: " + path);
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

static AssembledProgram load_and_assemble(const std::string& path) {
    std::string src = read_file(path);
    Assembler assembler;
    return assembler.assemble(src);
}

static int handle_assemble(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Error: 'assemble' requires a source file path.\n";
        return 1;
    }
    std::string asm_path = argv[2];
    std::string out_path;

    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "-o" && i + 1 < argc) {
            out_path = argv[++i];
        }
    }

    try {
        AssembledProgram prog = load_and_assemble(asm_path);
        auto hex_lines = prog.to_hex_lines();

        if (!out_path.empty()) {
            std::ofstream out(out_path);
            if (!out.is_open()) {
                std::cerr << "Error: Could not open output file: " << out_path << "\n";
                return 1;
            }
            for (const auto& line : hex_lines) {
                out << line << "\n";
            }
            std::cout << "[*] Assembled " << prog.text_words.size() << " instructions to '" << out_path << "'.\n";
        } else {
            std::cout << "=== RISC201 Machine Listing ===\n";
            for (const auto& line : hex_lines) {
                std::cout << line << "\n";
            }
            std::cout << "\nTotal Instructions: " << prog.text_words.size() << "\n";
            if (!prog.data_bytes.empty()) {
                std::cout << "Total Initialized Data: " << prog.data_bytes.size() << " bytes\n";
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[Assembler Error] " << e.what() << "\n";
        return 1;
    }
    return 0;
}

static int handle_disassemble(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Error: 'disassemble' requires a target (file or hex string).\n";
        return 1;
    }
    std::string target = argv[2];

    if (target.find(".hex") != std::string::npos || target.find(".txt") != std::string::npos) {
        try {
            std::ifstream file(target);
            if (!file.is_open()) {
                std::cerr << "Error: Could not open file: " << target << "\n";
                return 1;
            }
            std::string line;
            while (std::getline(file, line)) {
                size_t colon = line.find(':');
                if (colon != std::string::npos) {
                    std::string pc_str = line.substr(0, colon);
                    std::string rest = line.substr(colon + 1);
                    size_t semi = rest.find(';');
                    std::string word_str = (semi != std::string::npos) ? rest.substr(0, semi) : rest;
                    
                    uint32_t pc = std::stoul(pc_str, nullptr, 16);
                    uint32_t word = std::stoul(word_str, nullptr, 16);
                    std::cout << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << pc
                              << ": " << Disassembler::disassemble_word(word, pc) << "\n";
                }
            }
        } catch (const std::exception& e) {
            std::cerr << "[Disassembly Error] " << e.what() << "\n";
            return 1;
        }
    } else {
        try {
            uint32_t word = std::stoul(target, nullptr, 0);
            std::cout << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << word
                      << " --> " << Disassembler::disassemble_word(word) << "\n";
        } catch (...) {
            std::cerr << "Error: Invalid hexadecimal machine code format: " << target << "\n";
            return 1;
        }
    }
    return 0;
}

struct RunConfig {
    std::string file;
    std::string arch{"4stage"};
    bool enable_forwarding{true};
    PredictorMode branch_mode{PredictorMode::DYNAMIC_2BIT};
    bool vertical_micro{false};
    std::string set_reg;
    std::string set_mem;
};

template <typename CPU>
static void apply_custom_inputs(CPU& cpu, const RunConfig& cfg) {
    if (!cfg.set_reg.empty()) {
        std::stringstream ss(cfg.set_reg);
        std::string item;
        while (std::getline(ss, item, ',')) {
            size_t eq = item.find('=');
            if (eq != std::string::npos) {
                std::string k = item.substr(0, eq);
                std::string v = item.substr(eq + 1);
                k.erase(std::remove_if(k.begin(), k.end(), ::isspace), k.end());
                std::transform(k.begin(), k.end(), k.begin(), ::tolower);
                int reg_id = 0;
                if (k == "fp" || k == "r13") reg_id = 13;
                else if (k == "sp" || k == "r14") reg_id = 14;
                else if (k == "ra" || k == "r15") reg_id = 15;
                else if (!k.empty() && k[0] == 'r') reg_id = std::stoi(k.substr(1));
                else reg_id = std::stoi(k);
                int32_t val = static_cast<int32_t>(std::stoul(v, nullptr, 0));
                cpu.rf.write(reg_id, val);
                std::cout << "[*] Custom Input: Initialized r" << reg_id << " = " << val << "\n";
            }
        }
    }
    if (!cfg.set_mem.empty()) {
        std::stringstream ss(cfg.set_mem);
        std::string item;
        while (std::getline(ss, item, ',')) {
            size_t eq = item.find('=');
            if (eq != std::string::npos) {
                std::string addr_s = item.substr(0, eq);
                std::string val_s = item.substr(eq + 1);
                uint32_t addr = std::stoul(addr_s, nullptr, 0);
                int32_t val = static_cast<int32_t>(std::stoul(val_s, nullptr, 0));
                cpu.memory.write_word(addr, val);
                std::cout << "[*] Custom Input: Initialized mem[0x" << std::hex << addr << std::dec << "] = " << val << "\n";
            }
        }
    }
}

static RunConfig parse_run_args(int argc, char* argv[]) {
    RunConfig cfg;
    if (argc < 3) {
        throw std::runtime_error("Source file required.");
    }
    cfg.file = argv[2];

    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--arch" && i + 1 < argc) {
            cfg.arch = argv[++i];
        } else if (arg == "--no-forwarding") {
            cfg.enable_forwarding = false;
        } else if (arg == "--branch" && i + 1 < argc) {
            std::string bm = argv[++i];
            if (bm == "static_not_taken") cfg.branch_mode = PredictorMode::STATIC_NOT_TAKEN;
            else if (bm == "static_taken") cfg.branch_mode = PredictorMode::STATIC_TAKEN;
            else if (bm == "dynamic_2bit") cfg.branch_mode = PredictorMode::DYNAMIC_2BIT;
            else throw std::runtime_error("Unknown branch mode: " + bm);
        } else if (arg == "--vertical") {
            cfg.vertical_micro = true;
        } else if (arg == "--set-reg" && i + 1 < argc) {
            cfg.set_reg = argv[++i];
        } else if (arg == "--set-mem" && i + 1 < argc) {
            cfg.set_mem = argv[++i];
        }
    }
    return cfg;
}

static int handle_run(int argc, char* argv[]) {
    RunConfig cfg;
    try {
        cfg = parse_run_args(argc, argv);
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }

    try {
        AssembledProgram prog = load_and_assemble(cfg.file);
        std::cout << "[*] Running '" << cfg.file << "' on RISC201 [" << cfg.arch << "]...\n";

        if (cfg.arch == "4stage") {
            Processor4Stage cpu(cfg.enable_forwarding, cfg.branch_mode);
            cpu.memory.load_words(prog.text_start_addr, prog.text_words);
            if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
            apply_custom_inputs(cpu, cfg);
            cpu.run();

            if (cpu.exception_raised && cpu.last_exception) {
                std::cout << "\n[🚨 CPU EXCEPTION ENCOUNTERED]\n"
                          << "  " << cpu.last_exception->message << "\n"
                          << "  Trap Cause: " << get_cause_name(cpu.csr.cause) << "\n"
                          << "  EPC: 0x" << std::hex << std::uppercase << cpu.csr.epc << "\n";
            } else {
                std::cout << "[*] Execution finished successfully (Halted).\n";
            }
            std::cout << "\n" << cpu.pmc.format_summary() << "\n";
        } else if (cfg.arch == "6stage") {
            Processor6Stage cpu(cfg.enable_forwarding, cfg.branch_mode);
            cpu.memory.load_words(prog.text_start_addr, prog.text_words);
            if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
            apply_custom_inputs(cpu, cfg);
            cpu.run();

            if (cpu.exception_raised && cpu.last_exception) {
                std::cout << "\n[🚨 CPU EXCEPTION ENCOUNTERED]\n"
                          << "  " << cpu.last_exception->message << "\n"
                          << "  Trap Cause: " << get_cause_name(cpu.csr.cause) << "\n"
                          << "  EPC: 0x" << std::hex << std::uppercase << cpu.csr.epc << "\n";
            } else {
                std::cout << "[*] Execution finished successfully (Halted).\n";
            }
            std::cout << "\n" << cpu.pmc.format_summary() << "\n";
        } else if (cfg.arch == "micro") {
            MicroprogrammedCPU cpu(cfg.vertical_micro);
            cpu.memory.load_words(prog.text_start_addr, prog.text_words);
            if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
            apply_custom_inputs(cpu, cfg);
            cpu.run();

            if (cpu.csr.cause != CSRCause::NONE) {
                std::cout << "\n[🚨 CPU EXCEPTION ENCOUNTERED]\n"
                          << "  Trap Cause: " << get_cause_name(cpu.csr.cause) << "\n"
                          << "  EPC: 0x" << std::hex << std::uppercase << cpu.csr.epc << "\n";
            } else {
                std::cout << "[*] Execution finished successfully (Halted).\n";
            }
            std::cout << "\n" << cpu.pmc.format_summary() << "\n";
        } else {
            std::cerr << "Error: Unknown architecture: " << cfg.arch << "\n";
            return 1;
        }
    } catch (const std::exception& e) {
        std::cerr << "[Execution Error] " << e.what() << "\n";
        return 1;
    }
    return 0;
}

static int handle_debug(int argc, char* argv[]) {
    RunConfig cfg;
    try {
        cfg = parse_run_args(argc, argv);
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }

    try {
        AssembledProgram prog = load_and_assemble(cfg.file);

        if (cfg.arch == "4stage") {
            Processor4Stage cpu(cfg.enable_forwarding, cfg.branch_mode);
            cpu.memory.load_words(prog.text_start_addr, prog.text_words);
            if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
            apply_custom_inputs(cpu, cfg);
            CLIDebugger debugger(&cpu, prog);
            debugger.run_repl();
        } else if (cfg.arch == "6stage") {
            Processor6Stage cpu(cfg.enable_forwarding, cfg.branch_mode);
            cpu.memory.load_words(prog.text_start_addr, prog.text_words);
            if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
            apply_custom_inputs(cpu, cfg);
            CLIDebugger debugger(&cpu, prog);
            debugger.run_repl();
        } else if (cfg.arch == "micro") {
            MicroprogrammedCPU cpu(cfg.vertical_micro);
            cpu.memory.load_words(prog.text_start_addr, prog.text_words);
            if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
            apply_custom_inputs(cpu, cfg);
            CLIDebugger debugger(&cpu, prog);
            debugger.run_repl();
        } else {
            std::cerr << "Error: Unknown architecture: " << cfg.arch << "\n";
            return 1;
        }
    } catch (const std::exception& e) {
        std::cerr << "[Debugger Error] " << e.what() << "\n";
        return 1;
    }
    return 0;
}

static int handle_benchmark() {
    std::cout << "Starting RISC201 Architectural Benchmark Suite (C++17)...\n";
    benchmark_pipelines();
    benchmark_forwarding();
    benchmark_branch_predictors();
    benchmark_microcode();
    benchmark_alu_algorithms();
    benchmark_security_canary();
    std::cout << "\n================================================================================\n";
    std::cout << " ALL BENCHMARK EVALUATIONS COMPLETED SUCCESSFULLY.\n";
    std::cout << "================================================================================\n\n";
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    std::string cmd = argv[1];
    if (cmd == "-h" || cmd == "--help" || cmd == "help") {
        print_usage(argv[0]);
        return 0;
    } else if (cmd == "assemble") {
        return handle_assemble(argc, argv);
    } else if (cmd == "disassemble") {
        return handle_disassemble(argc, argv);
    } else if (cmd == "run") {
        return handle_run(argc, argv);
    } else if (cmd == "debug") {
        return handle_debug(argc, argv);
    } else if (cmd == "benchmark") {
        return handle_benchmark();
    } else {
        std::cerr << "Error: Unknown command '" << cmd << "'.\n";
        print_usage(argv[0]);
        return 1;
    }
}
