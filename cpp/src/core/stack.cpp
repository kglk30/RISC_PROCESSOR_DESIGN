#include "core/stack.hpp"
#include <sstream>
#include <algorithm>
#include <unordered_set>

namespace risc201 {

StackPreprocessor::StackPreprocessor(int32_t can, bool opt_leaf) : canary(can), optimize_leaf(opt_leaf) {}

static std::string trim(const std::string& str) {
    size_t first = str.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, (last - first + 1));
}

static std::pair<int, bool> parse_frame_args(const std::string& op, const std::vector<std::string>& args) {
    bool is_leaf = (op == "enter_leaf" || op == "leave_leaf");
    int frame_size = 0;
    for (const auto& a : args) {
        std::string lower_a = a;
        std::transform(lower_a.begin(), lower_a.end(), lower_a.begin(), ::tolower);
        if (lower_a == "leaf") {
            is_leaf = true;
        } else {
            try {
                frame_size = std::stoi(a);
            } catch (...) {}
        }
    }
    return {frame_size, is_leaf};
}

std::vector<std::string> StackPreprocessor::expand_lines(const std::vector<std::string>& lines) {
    // Pre-scan for automatic leaf detection if optimize_leaf is enabled
    std::unordered_set<size_t> auto_leaf_indices;
    if (optimize_leaf) {
        std::vector<std::pair<size_t, bool>> enter_stack; // (index, has_call)
        for (size_t i = 0; i < lines.size(); ++i) {
            size_t c1 = lines[i].find(';');
            size_t c2 = lines[i].find('#');
            size_t comm = std::min(c1 != std::string::npos ? c1 : lines[i].size(),
                                   c2 != std::string::npos ? c2 : lines[i].size());
            std::string cleaned = trim(lines[i].substr(0, comm));
            size_t colon_pos = cleaned.find(':');
            if (colon_pos != std::string::npos) {
                cleaned = trim(cleaned.substr(colon_pos + 1));
            }
            if (cleaned.empty()) continue;

            std::stringstream ss(cleaned);
            std::string cmd;
            ss >> cmd;
            std::transform(cmd.begin(), cmd.end(), cmd.begin(), ::tolower);

            if (cmd == "enter" || cmd == "enter_leaf") {
                enter_stack.push_back({i, false});
            } else if (cmd == "call" && !enter_stack.empty()) {
                enter_stack.back().second = true;
            } else if ((cmd == "leave" || cmd == "leave_leaf") && !enter_stack.empty()) {
                auto top = enter_stack.back();
                enter_stack.pop_back();
                if (!top.second) {
                    auto_leaf_indices.insert(top.first);
                    auto_leaf_indices.insert(i);
                }
            }
        }
    }

    std::vector<std::string> expanded;

    for (size_t line_idx = 0; line_idx < lines.size(); ++line_idx) {
        const auto& line = lines[line_idx];
        // Strip comments first
        size_t c1 = line.find(';');
        size_t c2 = line.find('#');
        size_t comm = std::min(c1 != std::string::npos ? c1 : line.size(),
                               c2 != std::string::npos ? c2 : line.size());
        std::string cleaned = trim(line.substr(0, comm));

        if (cleaned.empty()) {
            expanded.push_back(line);
            continue;
        }

        // Check for label on the same line
        std::string label_prefix = "";
        size_t colon_pos = cleaned.find(':');
        if (colon_pos != std::string::npos) {
            label_prefix = trim(cleaned.substr(0, colon_pos)) + ": ";
            cleaned = trim(cleaned.substr(colon_pos + 1));
        }

        if (cleaned.empty()) {
            expanded.push_back(label_prefix);
            continue;
        }

        // Tokenize
        std::stringstream ss(cleaned);
        std::string op;
        ss >> op;
        std::transform(op.begin(), op.end(), op.begin(), ::tolower);

        std::string rest;
        std::getline(ss, rest);
        std::vector<std::string> args;
        std::stringstream ss_args(rest);
        std::string token;
        while (std::getline(ss_args, token, ',')) {
            std::string t = trim(token);
            if (!t.empty()) args.push_back(t);
        }

        if (op == "push") {
            std::string reg = args.empty() ? "r1" : args[0];
            expanded.push_back(label_prefix + "sub sp, sp, 4");
            expanded.push_back("st " + reg + ", 0[sp]");
        } else if (op == "pop") {
            std::string reg = args.empty() ? "r1" : args[0];
            expanded.push_back(label_prefix + "ld " + reg + ", 0[sp]");
            expanded.push_back("add sp, sp, 4");
        } else if (op == "enter" || op == "enter_leaf") {
            auto [frame_size, is_leaf] = parse_frame_args(op, args);
            if (auto_leaf_indices.count(line_idx)) is_leaf = true;

            if (is_leaf) {
                // Leaf Function Optimization: avoids saving return address and frame pointer
                expanded.push_back(label_prefix + "; --- [enter leaf prologue: avoids saving ra & fp] ---");
                if (frame_size > 0) {
                    expanded.push_back("sub sp, sp, " + std::to_string(frame_size) + "        ; allocate local vars (leaf)");
                }
            } else {
                label_counter++;
                expanded.push_back(label_prefix + "; --- [enter prologue with canary] ---");
                expanded.push_back("sub sp, sp, 4");
                expanded.push_back("st ra, 0[sp]            ; save return address");
                expanded.push_back("sub sp, sp, 4");
                expanded.push_back("st fp, 0[sp]            ; save frame pointer");
                expanded.push_back("mov fp, sp              ; set fp to current sp");
                expanded.push_back("sub sp, sp, 4           ; allocate canary slot");
                expanded.push_back("mov r12, " + std::to_string(canary) + "   ; load canary magic using scratch r12");
                expanded.push_back("st r12, 0[sp]           ; store canary");
                if (frame_size > 0) {
                    expanded.push_back("sub sp, sp, " + std::to_string(frame_size) + "        ; allocate local vars");
                }
            }
        } else if (op == "leave" || op == "leave_leaf") {
            auto [frame_size, is_leaf] = parse_frame_args(op, args);
            if (auto_leaf_indices.count(line_idx)) is_leaf = true;

            if (is_leaf) {
                // Leaf Function Optimization: avoids restoring frame pointer and return address
                expanded.push_back(label_prefix + "; --- [leave leaf epilogue: avoids restoring ra & fp] ---");
                if (frame_size > 0) {
                    expanded.push_back("add sp, sp, " + std::to_string(frame_size) + "        ; deallocate local vars (leaf)");
                }
                expanded.push_back("ret");
            } else {
                std::string ok_label = "__canary_ok_" + std::to_string(label_counter++);
                expanded.push_back(label_prefix + "; --- [leave epilogue with canary check] ---");
                if (frame_size > 0) {
                    expanded.push_back("add sp, sp, " + std::to_string(frame_size) + "        ; deallocate local vars");
                }
                expanded.push_back("ld r12, 0[sp]           ; load canary using scratch r12");
                expanded.push_back("cmp r12, " + std::to_string(canary) + "  ; verify canary integrity");
                expanded.push_back("beq " + ok_label);
                expanded.push_back("trap 6                  ; STACK_CANARY_CORRUPTED exception!");
                expanded.push_back(ok_label + ":");
                expanded.push_back("add sp, sp, 4           ; pop canary");
                expanded.push_back("ld fp, 0[sp]            ; restore frame pointer");
                expanded.push_back("add sp, sp, 4");
                expanded.push_back("ld ra, 0[sp]            ; restore return address");
                expanded.push_back("add sp, sp, 4");
                expanded.push_back("ret");
            }
        } else {
            expanded.push_back(label_prefix.empty() ? line : label_prefix + cleaned);
        }
    }

    return expanded;
}

} // namespace risc201
