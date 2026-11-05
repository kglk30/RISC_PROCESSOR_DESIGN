CXX ?= clang++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -Iinclude
LDFLAGS = 

SRC_DIR = src
OBJ_DIR = obj
BIN_DIR = bin

COMMON_SRCS = \
	$(SRC_DIR)/core/isa.cpp \
	$(SRC_DIR)/core/registers.cpp \
	$(SRC_DIR)/core/memory.cpp \
	$(SRC_DIR)/core/stack.cpp \
	$(SRC_DIR)/core/pmc.cpp \
	$(SRC_DIR)/alu/alu.cpp \
	$(SRC_DIR)/pipelines/branch_predictor.cpp \
	$(SRC_DIR)/pipelines/forwarding.cpp \
	$(SRC_DIR)/pipelines/pipeline_4stage.cpp \
	$(SRC_DIR)/pipelines/pipeline_6stage.cpp \
	$(SRC_DIR)/control/microcode.cpp \
	$(SRC_DIR)/toolchain/assembler.cpp \
	$(SRC_DIR)/toolchain/disassembler.cpp \
	$(SRC_DIR)/ui/visualizer.cpp \
	$(SRC_DIR)/ui/debugger.cpp

COMMON_OBJS = $(patsubst $(SRC_DIR)/%.cpp, $(OBJ_DIR)/%.o, $(COMMON_SRCS))

TARGET_CLI = $(BIN_DIR)/risc201
TARGET_TEST = $(BIN_DIR)/test_all
TARGET_BENCH = $(BIN_DIR)/benchmark

.PHONY: all clean test run_benchmark

all: $(TARGET_CLI) $(TARGET_TEST) $(TARGET_BENCH)

$(TARGET_CLI): $(COMMON_OBJS) $(OBJ_DIR)/benchmark_lib.o $(OBJ_DIR)/main.o | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) $^ -o $@

$(TARGET_TEST): $(COMMON_OBJS) $(OBJ_DIR)/test_all.o | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) $^ -o $@

$(TARGET_BENCH): $(COMMON_OBJS) $(OBJ_DIR)/benchmark.o | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) $^ -o $@

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(OBJ_DIR)/benchmark_lib.o: $(SRC_DIR)/benchmark.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DNO_BENCHMARK_MAIN -c $< -o $@

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

test: $(TARGET_TEST)
	@echo "=== Running C++ RISC201 Unit Tests ==="
	@./$(TARGET_TEST)

run_benchmark: $(TARGET_BENCH)
	@echo "=== Running C++ RISC201 Benchmarks ==="
	@./$(TARGET_BENCH)

clean:
	rm -rf $(OBJ_DIR) $(BIN_DIR)
