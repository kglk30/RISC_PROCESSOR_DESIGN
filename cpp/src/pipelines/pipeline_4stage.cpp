#include "pipelines/pipeline_4stage.hpp"
#include <sstream>
#include <iomanip>

namespace risc201 {

Processor4Stage::Processor4Stage(bool fwd, PredictorMode bm)
    : branch_predictor(bm), hazard_unit(fwd) {
    reset(0);
}

void Processor4Stage::reset(uint32_t initial_pc) {
    pc = initial_pc;
    halted = false;
    exception_raised = false;
    last_exception = std::nullopt;
    rf.reset(memory.stack_base);
    csr.clear_exception();
    pmc.reset();
    branch_predictor.reset();
    if_id.clear();
    id_ex.clear();
    ex_wb.clear();
}

std::unordered_map<std::string, std::string> Processor4Stage::get_stage_strings() const {
    auto fmt = [](const std::optional<DecodedInstruction>& inst, uint32_t p) -> std::string {
        if (!inst) return "NOP (Bubble)";
        std::stringstream ss;
        ss << "0x" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << p
           << ": " << inst->op_name() << " (raw 0x" << std::setw(8) << inst->raw << ")";
        return ss.str();
    };

    std::string if_str = halted ? "HALTED" : "Fetching PC=0x" + [&]() {
        std::stringstream ss;
        ss << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << pc;
        return ss.str();
    }();

    return {
        {"IF", if_str},
        {"ID/OF", fmt(if_id.valid ? std::make_optional(decode_instruction(if_id.raw_word)) : std::nullopt, if_id.pc)},
        {"EX/MEM", fmt(id_ex.inst, id_ex.pc)},
        {"WB", fmt(ex_wb.inst, ex_wb.pc)}
    };
}

bool Processor4Stage::step() {
    if (halted) return false;

    pmc.tick_cycle();
    rf.clear_modified_flags();

    try {
        _stage_wb();
        Latch_EX_WB_4 next_ex_wb = _stage_ex_mem();
        auto [stall_id, flush_if, next_id_ex] = _stage_id_of(next_ex_wb);

        if (!stall_id) {
            if_id = _stage_if(flush_if);
        } else {
            pmc.record_stall(true);
        }

        ex_wb = next_ex_wb;
        id_ex = next_id_ex;

    } catch (const CPUException& e) {
        exception_raised = true;
        last_exception = e;
        halted = true;
        csr.trigger_exception(e.cause, e.pc, e.badvaddr);
        return false;
    }

    if (!if_id.valid && !id_ex.valid && !ex_wb.valid && halted) {
        return false;
    }

    return true;
}

void Processor4Stage::_stage_wb() {
    if (!ex_wb.valid || !ex_wb.inst) return;

    const auto& inst = *ex_wb.inst;
    if (inst.opcode == Opcode::HLT) {
        halted = true;
        pmc.commit_instruction();
        return;
    }

    if (inst.writes_rf()) {
        int32_t wb_val = (inst.opcode == Opcode::LD) ? ex_wb.mem_data : ex_wb.alu_result;
        rf.write(inst.dest_reg(), wb_val);
    }

    memory.check_stack_safety(rf.sp(), ex_wb.pc);
    pmc.commit_instruction();
}

Latch_EX_WB_4 Processor4Stage::_stage_ex_mem() {
    Latch_EX_WB_4 out;
    if (!id_ex.valid || !id_ex.inst) return out;

    const auto& inst = *id_ex.inst;
    uint32_t p = id_ex.pc;
    int32_t valA = id_ex.valA;
    int32_t valB = id_ex.valB;

    // Forwarding from previous instruction (now in ex_wb)
    if (hazard_unit.enable_forwarding) {
        if (ex_wb.valid && ex_wb.inst && ex_wb.inst->writes_rf() && ex_wb.inst->dest_reg() != 0) {
            int32_t fwd_val = (ex_wb.inst->opcode == Opcode::LD) ? ex_wb.mem_data : ex_wb.alu_result;
            uint8_t fdest = ex_wb.inst->dest_reg();

            if (inst.reads_rs1() && fdest == inst.rs1) {
                valA = fwd_val;
                pmc.record_forwarding();
            }
            if (inst.opcode == Opcode::ST && fdest == inst.rd) {
                valB = fwd_val;
                pmc.record_forwarding();
            } else if (inst.opcode == Opcode::MOV && !inst.is_imm && fdest == inst.rs1) {
                valB = fwd_val;
                pmc.record_forwarding();
            } else if (!inst.is_imm && inst.reads_rs2() && fdest == inst.rs2) {
                valB = fwd_val;
                pmc.record_forwarding();
            }
        }
    }

    int32_t alu_res = 0;
    int32_t mem_data = 0;

    if (inst.opcode == Opcode::TRAP) {
        throw CPUException(static_cast<CSRCause>(inst.trap_id), p, "TRAP triggered with code " + std::to_string(inst.trap_id));
    }

    if (inst.opcode == Opcode::CALL) {
        alu_res = static_cast<int32_t>(p + 4);
    } else if (is_memory_op(inst.opcode)) {
        uint32_t addr = static_cast<uint32_t>(valA + inst.imm);
        alu_res = static_cast<int32_t>(addr);
        if (inst.opcode == Opcode::LD) {
            mem_data = memory.read_word(addr, p);
        } else if (inst.opcode == Opcode::ST) {
            memory.write_word(addr, valB, p);
        }
    } else if (inst.opcode != Opcode::NOP && inst.opcode != Opcode::HLT && !is_branch_op(inst.opcode)) {
        try {
            alu_res = alu.execute(inst.opcode, valA, valB, true);
        } catch (const DivisionByZeroException&) {
            throw CPUException(CSRCause::DIVISION_BY_ZERO, p, "Division by zero encountered in ALU");
        }
    }

    out.valid = true;
    out.pc = p;
    out.inst = inst;
    out.alu_result = alu_res;
    out.mem_data = mem_data;
    return out;
}

std::tuple<bool, bool, Latch_ID_EX_4> Processor4Stage::_stage_id_of(const Latch_EX_WB_4& next_ex_wb) {
    Latch_ID_EX_4 out;
    if (!if_id.valid) return {false, false, out};

    DecodedInstruction inst = decode_instruction(if_id.raw_word);
    uint32_t p = if_id.pc;

    if (hazard_unit.check_load_use_hazard(inst, id_ex.inst)) {
        return {true, false, out};
    }

    if (!hazard_unit.enable_forwarding) {
        if (hazard_unit.check_raw_hazard_without_forwarding(inst, id_ex.inst, ex_wb.inst)) {
            pmc.record_stall(false);
            return {true, false, out};
        }
    }

    int32_t valA = rf.read(inst.rs1);
    int32_t valB = 0;

    if (inst.opcode == Opcode::ST) {
        valB = rf.read(inst.rd);
    } else if (inst.is_imm) {
        valB = inst.imm;
    } else if (inst.opcode == Opcode::MOV) {
        valB = rf.read(inst.rs1);
    } else {
        valB = rf.read(inst.rs2);
    }

    // Forwarding from next_ex_wb
    if (hazard_unit.enable_forwarding && next_ex_wb.valid && next_ex_wb.inst && next_ex_wb.inst->writes_rf()) {
        uint8_t fdest = next_ex_wb.inst->dest_reg();
        if (fdest != 0) {
            int32_t fwd_val = (next_ex_wb.inst->opcode == Opcode::LD) ? next_ex_wb.mem_data : next_ex_wb.alu_result;
            if (inst.reads_rs1() && fdest == inst.rs1) {
                valA = fwd_val;
                pmc.record_forwarding();
            }
            if (inst.opcode == Opcode::ST && fdest == inst.rd) {
                valB = fwd_val;
                pmc.record_forwarding();
            } else if (inst.opcode == Opcode::MOV && !inst.is_imm && fdest == inst.rs1) {
                valB = fwd_val;
                pmc.record_forwarding();
            } else if (!inst.is_imm && inst.reads_rs2() && fdest == inst.rs2) {
                valB = fwd_val;
                pmc.record_forwarding();
            }
        }
    }

    // Forwarding from ex_wb
    if (hazard_unit.enable_forwarding && ex_wb.valid && ex_wb.inst && ex_wb.inst->writes_rf()) {
        uint8_t fdest = ex_wb.inst->dest_reg();
        if (fdest != 0) {
            int32_t fwd_val = (ex_wb.inst->opcode == Opcode::LD) ? ex_wb.mem_data : ex_wb.alu_result;
            if (inst.reads_rs1() && fdest == inst.rs1) {
                valA = fwd_val;
                pmc.record_forwarding();
            }
            if (inst.opcode == Opcode::ST && fdest == inst.rd) {
                valB = fwd_val;
                pmc.record_forwarding();
            } else if (inst.opcode == Opcode::MOV && !inst.is_imm && fdest == inst.rs1) {
                valB = fwd_val;
                pmc.record_forwarding();
            } else if (!inst.is_imm && inst.reads_rs2() && fdest == inst.rs2) {
                valB = fwd_val;
                pmc.record_forwarding();
            }
        }
    }

    bool flush_if = false;
    if (is_branch_op(inst.opcode)) {
        bool actual_taken = false;
        uint32_t actual_target = p + 4;

        if (inst.opcode == Opcode::B) {
            actual_taken = true;
            actual_target = p + (inst.offset * 4);
        } else if (inst.opcode == Opcode::CALL) {
            actual_taken = true;
            actual_target = p + (inst.offset * 4);
        } else if (inst.opcode == Opcode::RET) {
            actual_taken = true;
            actual_target = static_cast<uint32_t>(rf.ra());
        } else if (inst.opcode == Opcode::BEQ) {
            actual_taken = alu.flags.Z;
            actual_target = p + (inst.offset * 4);
        } else if (inst.opcode == Opcode::BNE) {
            actual_taken = !alu.flags.Z;
            actual_target = p + (inst.offset * 4);
        } else if (inst.opcode == Opcode::BGT) {
            actual_taken = !alu.flags.Z && (alu.flags.N == alu.flags.V);
            actual_target = p + (inst.offset * 4);
        } else if (inst.opcode == Opcode::BLT) {
            actual_taken = (alu.flags.N != alu.flags.V);
            actual_target = p + (inst.offset * 4);
        }

        bool pred_taken = if_id.pred_taken;
        uint32_t pred_target = if_id.pred_target;
        bool mispredicted = (actual_taken != pred_taken) || (actual_taken && pred_target != actual_target);

        pmc.record_branch(mispredicted);
        branch_predictor.update(p, inst.opcode, actual_taken, actual_target);

        if (mispredicted) {
            pc = actual_taken ? actual_target : (p + 4);
            flush_if = true;
        }
    }

    out.valid = true;
    out.pc = p;
    out.inst = inst;
    out.valA = valA;
    out.valB = valB;
    return {false, flush_if, out};
}

Latch_IF_ID_4 Processor4Stage::_stage_if(bool flush) {
    Latch_IF_ID_4 out;
    if (flush || halted || pc >= memory.size) return out;
    if (if_id.valid && (if_id.raw_word >> 27) == static_cast<uint32_t>(Opcode::HLT)) return out;
    if (id_ex.valid && id_ex.inst && id_ex.inst->opcode == Opcode::HLT) return out;
    if (ex_wb.valid && ex_wb.inst && ex_wb.inst->opcode == Opcode::HLT) return out;

    uint32_t raw = static_cast<uint32_t>(memory.read_word(pc, pc));
    DecodedInstruction inst = decode_instruction(raw);

    auto [pred_taken, pred_target] = branch_predictor.predict(pc, inst.opcode, pc + 4);

    out.valid = true;
    out.pc = pc;
    out.raw_word = raw;
    out.pred_taken = pred_taken;
    out.pred_target = pred_target;

    pc = pred_taken ? pred_target : (pc + 4);
    return out;
}

bool Processor4Stage::run(uint64_t max_cycles) {
    uint64_t cycles = 0;
    while (!halted && cycles < max_cycles) {
        cycles++;
        if (!step()) break;
    }
    return halted;
}

} // namespace risc201
