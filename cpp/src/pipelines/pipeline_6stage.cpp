#include "pipelines/pipeline_6stage.hpp"
#include <sstream>
#include <iomanip>

namespace risc201 {

Processor6Stage::Processor6Stage(bool fwd, PredictorMode bm)
    : branch_predictor(bm), hazard_unit(fwd) {
    reset(0);
}

void Processor6Stage::reset(uint32_t initial_pc) {
    pc = initial_pc;
    halted = false;
    exception_raised = false;
    last_exception = std::nullopt;
    rf.reset(memory.stack_base);
    csr.clear_exception();
    pmc.reset();
    branch_predictor.reset();
    if_id.clear();
    id_rr.clear();
    rr_ex.clear();
    ex_mem.clear();
    mem_wb.clear();
}

std::unordered_map<std::string, std::string> Processor6Stage::get_stage_strings() const {
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
        {"ID", fmt(if_id.valid ? std::make_optional(decode_instruction(if_id.raw_word)) : std::nullopt, if_id.pc)},
        {"RR", fmt(id_rr.inst, id_rr.pc)},
        {"EX", fmt(rr_ex.inst, rr_ex.pc)},
        {"MEM", fmt(ex_mem.inst, ex_mem.pc)},
        {"WB", fmt(mem_wb.inst, mem_wb.pc)}
    };
}

bool Processor6Stage::step() {
    if (halted) return false;

    pmc.tick_cycle();
    rf.clear_modified_flags();

    try {
        _stage_wb();
        Latch_MEM_WB_6 next_mem_wb = _stage_mem();
        auto [branch_flush, next_ex_mem] = _stage_ex();
        auto [stall_pipeline, next_rr_ex] = _stage_rr();

        Latch_ID_RR_6 next_id_rr;
        if (!stall_pipeline) {
            if (if_id.valid) {
                next_id_rr.valid = true;
                next_id_rr.pc = if_id.pc;
                next_id_rr.inst = decode_instruction(if_id.raw_word);
                next_id_rr.pred_taken = if_id.pred_taken;
                next_id_rr.pred_target = if_id.pred_target;
            }
        } else {
            next_id_rr = id_rr;
        }

        Latch_IF_ID_6 next_if_id = if_id;
        if (branch_flush) {
            if_id.clear();
            id_rr.clear();
            next_rr_ex.clear();
            next_id_rr.clear();
        } else if (!stall_pipeline) {
            next_if_id = _stage_if();
        } else {
            pmc.record_stall(true);
        }

        mem_wb = next_mem_wb;
        ex_mem = next_ex_mem;

        if (branch_flush) {
            if_id.clear();
            id_rr.clear();
            rr_ex.clear();
        } else {
            rr_ex = next_rr_ex;
            id_rr = next_id_rr;
            if (!stall_pipeline) {
                if_id = next_if_id;
            }
        }

    } catch (const CPUException& e) {
        exception_raised = true;
        last_exception = e;
        halted = true;
        csr.trigger_exception(e.cause, e.pc, e.badvaddr);
        return false;
    }

    if (!if_id.valid && !id_rr.valid && !rr_ex.valid && !ex_mem.valid && !mem_wb.valid && halted) {
        return false;
    }

    return true;
}

void Processor6Stage::_stage_wb() {
    if (!mem_wb.valid || !mem_wb.inst) return;

    const auto& inst = *mem_wb.inst;
    if (inst.opcode == Opcode::HLT) {
        halted = true;
        pmc.commit_instruction();
        return;
    }

    if (inst.writes_rf()) {
        int32_t wb_val = (inst.opcode == Opcode::LD) ? mem_wb.mem_data : mem_wb.alu_result;
        rf.write(inst.dest_reg(), wb_val);
    }

    memory.check_stack_safety(rf.sp(), mem_wb.pc);
    pmc.commit_instruction();
}

Latch_MEM_WB_6 Processor6Stage::_stage_mem() {
    Latch_MEM_WB_6 out;
    if (!ex_mem.valid || !ex_mem.inst) return out;

    const auto& inst = *ex_mem.inst;
    uint32_t p = ex_mem.pc;
    int32_t alu_res = ex_mem.alu_result;
    int32_t mem_data = 0;

    if (inst.opcode == Opcode::LD) {
        mem_data = memory.read_word(static_cast<uint32_t>(alu_res), p);
    } else if (inst.opcode == Opcode::ST) {
        int32_t store_val = ex_mem.store_val;
        // MEM-to-MEM forwarding
        if (hazard_unit.enable_forwarding && mem_wb.valid && mem_wb.inst &&
            mem_wb.inst->opcode == Opcode::LD && mem_wb.inst->dest_reg() == inst.rd && inst.rd != 0) {
            store_val = mem_wb.mem_data;
            pmc.record_forwarding();
        }
        memory.write_word(static_cast<uint32_t>(alu_res), store_val, p);
    }

    out.valid = true;
    out.pc = p;
    out.inst = inst;
    out.alu_result = alu_res;
    out.mem_data = mem_data;
    return out;
}

std::pair<bool, Latch_EX_MEM_6> Processor6Stage::_stage_ex() {
    Latch_EX_MEM_6 out;
    bool branch_flush = false;
    if (!rr_ex.valid || !rr_ex.inst) return {branch_flush, out};

    const auto& inst = *rr_ex.inst;
    uint32_t p = rr_ex.pc;
    int32_t valA = rr_ex.valA;
    int32_t valB = rr_ex.valB;
    int32_t store_val = rr_ex.store_val;

    // Forwarding MUX at ALU inputs
    if (hazard_unit.enable_forwarding) {
        // Operand A
        if (inst.reads_rs1() && inst.rs1 != 0) {
            if (ex_mem.valid && ex_mem.inst && ex_mem.inst->writes_rf() && ex_mem.inst->dest_reg() == inst.rs1) {
                valA = ex_mem.alu_result;
                pmc.record_forwarding();
            } else if (mem_wb.valid && mem_wb.inst && mem_wb.inst->writes_rf() && mem_wb.inst->dest_reg() == inst.rs1) {
                valA = (mem_wb.inst->opcode == Opcode::LD) ? mem_wb.mem_data : mem_wb.alu_result;
                pmc.record_forwarding();
            }
        }

        // Operand B
        if (inst.opcode == Opcode::MOV && !inst.is_imm && inst.rs1 != 0) {
            if (ex_mem.valid && ex_mem.inst && ex_mem.inst->writes_rf() && ex_mem.inst->dest_reg() == inst.rs1) {
                valB = ex_mem.alu_result;
                pmc.record_forwarding();
            } else if (mem_wb.valid && mem_wb.inst && mem_wb.inst->writes_rf() && mem_wb.inst->dest_reg() == inst.rs1) {
                valB = (mem_wb.inst->opcode == Opcode::LD) ? mem_wb.mem_data : mem_wb.alu_result;
                pmc.record_forwarding();
            }
        } else if (!inst.is_imm && inst.reads_rs2() && inst.rs2 != 0) {
            if (ex_mem.valid && ex_mem.inst && ex_mem.inst->writes_rf() && ex_mem.inst->dest_reg() == inst.rs2) {
                valB = ex_mem.alu_result;
                pmc.record_forwarding();
            } else if (mem_wb.valid && mem_wb.inst && mem_wb.inst->writes_rf() && mem_wb.inst->dest_reg() == inst.rs2) {
                valB = (mem_wb.inst->opcode == Opcode::LD) ? mem_wb.mem_data : mem_wb.alu_result;
                pmc.record_forwarding();
            }
        }

        // Store value
        if (inst.opcode == Opcode::ST && inst.rd != 0) {
            if (ex_mem.valid && ex_mem.inst && ex_mem.inst->writes_rf() && ex_mem.inst->dest_reg() == inst.rd) {
                store_val = ex_mem.alu_result;
                pmc.record_forwarding();
            } else if (mem_wb.valid && mem_wb.inst && mem_wb.inst->writes_rf() && mem_wb.inst->dest_reg() == inst.rd) {
                store_val = (mem_wb.inst->opcode == Opcode::LD) ? mem_wb.mem_data : mem_wb.alu_result;
                pmc.record_forwarding();
            }
        }
    }

    int32_t alu_res = 0;

    if (inst.opcode == Opcode::TRAP) {
        throw CPUException(static_cast<CSRCause>(inst.trap_id), p, "TRAP triggered with code " + std::to_string(inst.trap_id));
    }

    if (inst.opcode == Opcode::CALL) {
        alu_res = static_cast<int32_t>(p + 4);
    } else if (is_memory_op(inst.opcode)) {
        alu_res = valA + inst.imm;
    } else if (inst.opcode != Opcode::NOP && inst.opcode != Opcode::HLT && !is_branch_op(inst.opcode)) {
        try {
            alu_res = alu.execute(inst.opcode, valA, valB, true);
        } catch (const DivisionByZeroException&) {
            throw CPUException(CSRCause::DIVISION_BY_ZERO, p, "Division by zero encountered in ALU");
        }
    }

    // Branch resolution in EX stage
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

        bool pred_taken = rr_ex.pred_taken;
        uint32_t pred_target = rr_ex.pred_target;
        bool mispredicted = (actual_taken != pred_taken) || (actual_taken && pred_target != actual_target);

        pmc.record_branch(mispredicted);
        branch_predictor.update(p, inst.opcode, actual_taken, actual_target);

        if (mispredicted) {
            pc = actual_taken ? actual_target : (p + 4);
            branch_flush = true;
        }
    }

    out.valid = true;
    out.pc = p;
    out.inst = inst;
    out.alu_result = alu_res;
    out.store_val = store_val;
    return {branch_flush, out};
}

std::pair<bool, Latch_RR_EX_6> Processor6Stage::_stage_rr() {
    Latch_RR_EX_6 out;
    if (!id_rr.valid || !id_rr.inst) return {false, out};

    const auto& inst = *id_rr.inst;
    uint32_t p = id_rr.pc;

    if (hazard_unit.check_load_use_hazard(inst, rr_ex.inst)) {
        return {true, out};
    }

    if (!hazard_unit.enable_forwarding) {
        if (hazard_unit.check_raw_hazard_without_forwarding(inst, rr_ex.inst, ex_mem.inst)) {
            pmc.record_stall(false);
            return {true, out};
        }
    }

    int32_t valA = rf.read(inst.rs1);
    int32_t valB = 0;
    int32_t store_val = 0;

    if (inst.opcode == Opcode::ST) {
        valB = 0;
        store_val = rf.read(inst.rd);
    } else if (inst.is_imm) {
        valB = inst.imm;
    } else if (inst.opcode == Opcode::MOV) {
        valB = rf.read(inst.rs1);
    } else {
        valB = rf.read(inst.rs2);
    }

    // Write-to-read bypass
    if (mem_wb.valid && mem_wb.inst && mem_wb.inst->writes_rf()) {
        uint8_t wreg = mem_wb.inst->dest_reg();
        int32_t wval = (mem_wb.inst->opcode == Opcode::LD) ? mem_wb.mem_data : mem_wb.alu_result;
        if (wreg != 0) {
            if (inst.reads_rs1() && inst.rs1 == wreg) valA = wval;
            if (inst.opcode == Opcode::MOV && !inst.is_imm && inst.rs1 == wreg) valB = wval;
            else if (!inst.is_imm && inst.reads_rs2() && inst.rs2 == wreg) valB = wval;
            if (inst.opcode == Opcode::ST && inst.rd == wreg) store_val = wval;
        }
    }

    out.valid = true;
    out.pc = p;
    out.inst = inst;
    out.valA = valA;
    out.valB = valB;
    out.store_val = store_val;
    out.pred_taken = id_rr.pred_taken;
    out.pred_target = id_rr.pred_target;
    return {false, out};
}

Latch_IF_ID_6 Processor6Stage::_stage_if() {
    Latch_IF_ID_6 out;
    if (halted || pc >= memory.size) return out;
    if (if_id.valid && (if_id.raw_word >> 27) == static_cast<uint32_t>(Opcode::HLT)) return out;
    if (id_rr.valid && id_rr.inst && id_rr.inst->opcode == Opcode::HLT) return out;
    if (rr_ex.valid && rr_ex.inst && rr_ex.inst->opcode == Opcode::HLT) return out;
    if (ex_mem.valid && ex_mem.inst && ex_mem.inst->opcode == Opcode::HLT) return out;

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

bool Processor6Stage::run(uint64_t max_cycles) {
    uint64_t cycles = 0;
    while (!halted && cycles < max_cycles) {
        cycles++;
        if (!step()) break;
    }
    return halted;
}

} // namespace risc201
