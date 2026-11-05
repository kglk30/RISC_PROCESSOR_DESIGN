#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <optional>
#include "core/registers.hpp"

namespace risc201 {

class Memory {
public:
    static constexpr size_t DEFAULT_SIZE = 0x00010000;         // 64 KB
    static constexpr uint32_t DEFAULT_STACK_BASE = 0x00004000;
    static constexpr uint32_t DEFAULT_STACK_LIMIT = 0x00003000;
    static constexpr uint32_t DEFAULT_REDZONE_BASE = 0x00002C00;
    static constexpr uint32_t DEFAULT_REDZONE_LIMIT = 0x00003000;

    size_t size;
    uint32_t stack_base;
    uint32_t stack_limit;
    uint32_t redzone_base;
    uint32_t redzone_limit;

    std::vector<uint8_t> bytes;
    std::optional<uint32_t> last_written_addr{std::nullopt};
    std::unordered_map<uint32_t, int32_t> write_history;

    Memory(size_t sz = DEFAULT_SIZE,
           uint32_t sb = DEFAULT_STACK_BASE,
           uint32_t sl = DEFAULT_STACK_LIMIT,
           uint32_t rb = DEFAULT_REDZONE_BASE,
           uint32_t rl = DEFAULT_REDZONE_LIMIT);

    void reset();
    void check_alignment(uint32_t addr, uint32_t pc = 0) const;
    void check_bounds(uint32_t addr, uint32_t pc = 0) const;
    void check_stack_safety(uint32_t current_sp, uint32_t pc = 0) const;

    int32_t read_word(uint32_t addr, uint32_t pc = 0) const;
    void write_word(uint32_t addr, int32_t value, uint32_t pc = 0);

    void load_words(uint32_t start_addr, const std::vector<int32_t>& words);
    void load_bytes(uint32_t start_addr, const std::vector<uint8_t>& raw_data);
};

} // namespace risc201
