#include "control/microcode.hpp"
#include <vector>

namespace risc201 {

ControlStore::ControlStore() {
    build_microcode();
}

void ControlStore::build_microcode() {
    // 1. Fetch & Decode
    // uPC 0: Fetch
    horizontal_rom[0] = {true, 0, true, false, false, true, false, 1, 2, Opcode::ADD, MicroSeqOp::NEXT, 1, "FETCH_READ"};
    vertical_rom[0]   = {Opcode::ADD, 1, 0, 1, false, MicroSeqOp::NEXT, 1, "FETCH_READ"};

    // uPC 1: Decode & Dispatch
    horizontal_rom[1] = {false, 0, false, false, false, false, false, 0, 0, Opcode::NOP, MicroSeqOp::DISPATCH, 0, "DISPATCH"};
    vertical_rom[1]   = {Opcode::NOP, 0, 0, 0, false, MicroSeqOp::DISPATCH, 0, "DISPATCH"};

    // Operations
    std::vector<std::pair<Opcode, uint8_t>> ops = {
        {Opcode::ADD, 10}, {Opcode::SUB, 14}, {Opcode::MUL, 18}, {Opcode::DIV, 22},
        {Opcode::MOD, 24}, {Opcode::CMP, 26}, {Opcode::AND, 28}, {Opcode::OR,  30},
        {Opcode::NOT, 32}, {Opcode::MOV, 34}, {Opcode::LSL, 36}, {Opcode::LSR, 38},
        {Opcode::ASR, 40}
    };

    for (const auto& [op, addr] : ops) {
        dispatch_table[op] = addr;
        bool wr = (op != Opcode::CMP);
        std::string n = get_opcode_name(op) + "_EXEC_WB";
        horizontal_rom[addr] = {false, 0, false, false, false, false, wr, 0, 0, op, MicroSeqOp::FETCH, 0, n};
        vertical_rom[addr]   = {op, 0, 0, 0, wr, MicroSeqOp::FETCH, 0, n};
    }

    // LD: 50, 51
    dispatch_table[Opcode::LD] = 50;
    horizontal_rom[50] = {false, 0, true, false, false, false, false, 0, 1, Opcode::ADD, MicroSeqOp::NEXT, 51, "LD_ADDR_CALC"};
    vertical_rom[50]   = {Opcode::ADD, 0, 1, 1, false, MicroSeqOp::NEXT, 51, "LD_ADDR_CALC"};

    horizontal_rom[51] = {false, 0, false, false, true, false, true, 0, 0, Opcode::NOP, MicroSeqOp::FETCH, 0, "LD_MEM_WB"};
    vertical_rom[51]   = {Opcode::NOP, 0, 0, 0, true, MicroSeqOp::FETCH, 0, "LD_MEM_WB"};

    // ST: 54
    dispatch_table[Opcode::ST] = 54;
    horizontal_rom[54] = {false, 0, false, true, false, false, false, 0, 1, Opcode::ADD, MicroSeqOp::FETCH, 0, "ST_MEM_WRITE"};
    vertical_rom[54]   = {Opcode::ADD, 0, 2, 2, false, MicroSeqOp::FETCH, 0, "ST_MEM_WRITE"};

    // BEQ: 60
    dispatch_table[Opcode::BEQ] = 60;
    horizontal_rom[60] = {true, 1, false, false, false, false, false, 1, 1, Opcode::ADD, MicroSeqOp::BRANCH_COND, 0, "BEQ_EVAL"};
    vertical_rom[60]   = {Opcode::ADD, 1, 0, 0, false, MicroSeqOp::BRANCH_COND, 0, "BEQ_EVAL"};

    // B: 64
    dispatch_table[Opcode::B] = 64;
    horizontal_rom[64] = {true, 1, false, false, false, false, false, 1, 1, Opcode::ADD, MicroSeqOp::FETCH, 0, "B_JUMP"};
    vertical_rom[64]   = {Opcode::ADD, 1, 0, 0, false, MicroSeqOp::FETCH, 0, "B_JUMP"};

    // CALL: 68, 69
    dispatch_table[Opcode::CALL] = 68;
    horizontal_rom[68] = {false, 0, false, false, false, false, true, 1, 2, Opcode::ADD, MicroSeqOp::NEXT, 69, "CALL_SAVE_RA"};
    vertical_rom[68]   = {Opcode::ADD, 1, 0, 0, true, MicroSeqOp::NEXT, 69, "CALL_SAVE_RA"};

    horizontal_rom[69] = {true, 1, false, false, false, false, false, 1, 1, Opcode::ADD, MicroSeqOp::FETCH, 0, "CALL_TARGET"};
    vertical_rom[69]   = {Opcode::ADD, 1, 0, 0, false, MicroSeqOp::FETCH, 0, "CALL_TARGET"};

    // RET: 72
    dispatch_table[Opcode::RET] = 72;
    horizontal_rom[72] = {true, 2, false, false, false, false, false, 0, 0, Opcode::NOP, MicroSeqOp::FETCH, 0, "RET_RESTORE"};
    vertical_rom[72]   = {Opcode::NOP, 2, 0, 0, false, MicroSeqOp::FETCH, 0, "RET_RESTORE"};

    // HLT: 80
    dispatch_table[Opcode::HLT] = 80;
    horizontal_rom[80] = {false, 0, false, false, false, false, false, 0, 0, Opcode::NOP, MicroSeqOp::JUMP, 80, "HLT_HALT"};
    vertical_rom[80]   = {Opcode::NOP, 0, 0, 0, false, MicroSeqOp::JUMP, 80, "HLT_HALT"};
}

MicroprogrammedCPU::MicroprogrammedCPU(bool vertical) : use_vertical(vertical) {
    reset(0);
}

void MicroprogrammedCPU::reset(uint32_t initial_pc) {
    pc = initial_pc;
    ir = 0;
    mar = 0;
    mdr = 0;
    upc = 0;
    halted = false;
    total_micro_cycles = 0;
    current_inst = std::nullopt;
    rf.reset(memory.stack_base);
    csr.clear_exception();
    pmc.reset();
}

bool MicroprogrammedCPU::step_micro() {
    if (halted) return false;

    total_micro_cycles++;
    pmc.tick_cycle();

    MicroSeqOp seq_op = MicroSeqOp::NEXT;
    uint8_t next_addr = 0;
    bool reg_write = false;
    Opcode alu_func = Opcode::NOP;

    if (use_vertical) {
        auto it = store.vertical_rom.find(upc);
        if (it == store.vertical_rom.end()) {
            throw CPUException(CSRCause::ILLEGAL_INSTRUCTION, pc, "Invalid microPC: " + std::to_string(upc));
        }
        seq_op = it->second.seq_ctrl;
        next_addr = it->second.next_uaddr;
        reg_write = it->second.reg_write;
        alu_func = it->second.alu_func;
    } else {
        auto it = store.horizontal_rom.find(upc);
        if (it == store.horizontal_rom.end()) {
            throw CPUException(CSRCause::ILLEGAL_INSTRUCTION, pc, "Invalid microPC: " + std::to_string(upc));
        }
        seq_op = it->second.seq_op;
        next_addr = it->second.next_uaddr;
        reg_write = it->second.reg_write;
        alu_func = it->second.alu_op;
    }

    if (upc == 0) { // FETCH_READ
        ir = static_cast<uint32_t>(memory.read_word(pc, pc));
        current_inst = decode_instruction(ir);
        pc += 4;
    } else if (upc == 1) { // DISPATCH
        // handled in sequencer
    } else {
        if (current_inst) {
            const auto& inst = *current_inst;
            if (inst.opcode == Opcode::HLT) {
                halted = true;
                pmc.commit_instruction();
                return false;
            }

            int32_t valA = rf.read(inst.rs1);
            int32_t valB = 0;
            if (inst.is_imm) {
                valB = inst.imm;
            } else if (inst.opcode == Opcode::MOV) {
                valB = rf.read(inst.rs1);
            } else {
                valB = rf.read(inst.rs2);
            }

            int32_t res = 0;
            try {
                res = alu.execute(inst.opcode, valA, valB, true);
            } catch (const DivisionByZeroException&) {
                throw CPUException(CSRCause::DIVISION_BY_ZERO, pc - 4, "ALU Division by zero");
            }

            if (reg_write && inst.writes_rf()) {
                if (inst.opcode == Opcode::LD) {
                    uint32_t addr = static_cast<uint32_t>(valA + inst.imm);
                    int32_t loaded = memory.read_word(addr, pc - 4);
                    rf.write(inst.dest_reg(), loaded);
                } else if (inst.opcode == Opcode::CALL) {
                    rf.write(15, static_cast<int32_t>(pc));
                } else {
                    rf.write(inst.dest_reg(), res);
                }
            }

            if (inst.opcode == Opcode::ST) {
                uint32_t addr = static_cast<uint32_t>(valA + inst.imm);
                int32_t store_val = rf.read(inst.rd);
                memory.write_word(addr, store_val, pc - 4);
            }

            if (inst.opcode == Opcode::B) {
                pc = (pc - 4) + (inst.offset * 4);
            } else if (inst.opcode == Opcode::CALL) {
                pc = (pc - 4) + (inst.offset * 4);
            } else if (inst.opcode == Opcode::RET) {
                pc = static_cast<uint32_t>(rf.ra());
            } else if (inst.opcode == Opcode::BEQ && alu.flags.Z) {
                pc = (pc - 4) + (inst.offset * 4);
            }
        }
    }

    // Sequencer
    if (seq_op == MicroSeqOp::NEXT) {
        upc++;
    } else if (seq_op == MicroSeqOp::DISPATCH) {
        if (current_inst) {
            auto it = store.dispatch_table.find(current_inst->opcode);
            upc = (it != store.dispatch_table.end()) ? it->second : 0;
        } else {
            upc = 0;
        }
    } else if (seq_op == MicroSeqOp::FETCH) {
        upc = 0;
        pmc.commit_instruction();
    } else if (seq_op == MicroSeqOp::JUMP) {
        upc = next_addr;
    } else if (seq_op == MicroSeqOp::BRANCH_COND) {
        upc = 0;
        pmc.commit_instruction();
    }

    return true;
}

bool MicroprogrammedCPU::step_macro() {
    if (halted) return false;
    bool cont = step_micro();
    while (cont && upc != 0 && !halted) {
        cont = step_micro();
    }
    return cont;
}

bool MicroprogrammedCPU::run(uint64_t max_micro_cycles) {
    uint64_t cycles = 0;
    while (!halted && cycles < max_micro_cycles) {
        cycles++;
        if (!step_micro()) break;
    }
    return halted;
}

} // namespace risc201
