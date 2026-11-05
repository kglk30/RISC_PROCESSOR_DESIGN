#include "pipelines/forwarding.hpp"
#include <vector>

namespace risc201 {

bool HazardUnit::check_load_use_hazard(
    const std::optional<DecodedInstruction>& id_inst,
    const std::optional<DecodedInstruction>& ex_inst
) const {
    if (!id_inst || !ex_inst) return false;

    if (ex_inst->opcode == Opcode::LD && ex_inst->rd != 0) {
        if (id_inst->reads_rs1() && id_inst->rs1 == ex_inst->rd) return true;
        if (id_inst->reads_rs2() && id_inst->rs2 == ex_inst->rd) return true;
        if (id_inst->opcode == Opcode::ST && id_inst->rd == ex_inst->rd) return true;
    }
    return false;
}

bool HazardUnit::check_raw_hazard_without_forwarding(
    const std::optional<DecodedInstruction>& id_inst,
    const std::optional<DecodedInstruction>& ex_inst,
    const std::optional<DecodedInstruction>& mem_inst
) const {
    if (!id_inst) return false;

    std::vector<uint8_t> read_regs;
    if (id_inst->reads_rs1() && id_inst->rs1 != 0) read_regs.push_back(id_inst->rs1);
    if (id_inst->reads_rs2() && id_inst->rs2 != 0) read_regs.push_back(id_inst->rs2);
    if (id_inst->opcode == Opcode::ST && id_inst->rd != 0) read_regs.push_back(id_inst->rd);

    for (uint8_t reg : read_regs) {
        if (ex_inst && ex_inst->writes_rf() && ex_inst->dest_reg() == reg && reg != 0) {
            return true;
        }
        if (mem_inst && mem_inst->writes_rf() && mem_inst->dest_reg() == reg && reg != 0) {
            return true;
        }
    }

    return false;
}

} // namespace risc201
