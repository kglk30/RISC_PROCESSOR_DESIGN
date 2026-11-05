#pragma once

#include <optional>
#include "core/isa.hpp"

namespace risc201 {

class HazardUnit {
public:
    bool enable_forwarding{true};

    explicit HazardUnit(bool fwd = true) : enable_forwarding(fwd) {}

    bool check_load_use_hazard(
        const std::optional<DecodedInstruction>& id_inst,
        const std::optional<DecodedInstruction>& ex_inst
    ) const;

    bool check_raw_hazard_without_forwarding(
        const std::optional<DecodedInstruction>& id_inst,
        const std::optional<DecodedInstruction>& ex_inst,
        const std::optional<DecodedInstruction>& mem_inst
    ) const;
};

} // namespace risc201
