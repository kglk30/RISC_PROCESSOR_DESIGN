#pragma once

#include <string>
#include <unordered_set>
#include <unordered_map>
#include <memory>
#include <variant>
#include "pipelines/pipeline_4stage.hpp"
#include "pipelines/pipeline_6stage.hpp"
#include "control/microcode.hpp"
#include "toolchain/assembler.hpp"

namespace risc201 {

class CLIDebugger {
public:
    std::variant<Processor4Stage*, Processor6Stage*, MicroprogrammedCPU*> cpu_var;
    AssembledProgram program;
    std::unordered_set<uint32_t> breakpoints;
    std::unordered_map<std::string, uint32_t> symbol_to_addr;
    std::unordered_map<uint32_t, std::string> addr_to_symbol;
    int mode{0}; // 0 = 4stage, 1 = 6stage, 2 = micro

    CLIDebugger(Processor4Stage* c, const AssembledProgram& prog);
    CLIDebugger(Processor6Stage* c, const AssembledProgram& prog);
    CLIDebugger(MicroprogrammedCPU* c, const AssembledProgram& prog);

    void add_breakpoint(const std::string& target);
    void print_registers();
    void print_pipeline();
    void print_stack();
    void print_pmc();
    void print_disasm(int count = 8);
    void print_help();
    bool step_one();
    void run_repl();

private:
    uint32_t get_pc() const;
    bool is_halted() const;
    bool has_exception() const;
    void reset_cpu();
};

} // namespace risc201
