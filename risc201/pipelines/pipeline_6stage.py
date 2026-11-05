"""
RISC201 6-Stage Pipelined Processor
Stages:
  1. IF  : Instruction Fetch
  2. ID  : Instruction Decode & Control Word Generation
  3. RR  : Register Read / Operand Fetch
  4. EX  : ALU Execution & Branch Resolution
  5. MEM : Data Memory Access
  6. WB  : Write Back to Register File

Features:
- Hardwired Zero Register (r0)
- Full-Matrix Multiplexer Forwarding Network (EX-to-EX, MEM-to-EX, WB-to-EX)
- Dynamic 2-bit Saturating Counter Branch Predictor with BTB (resolved at EX)
- Hardware Performance Monitoring Counters (PMCs)
- CSR Exception Trapping and Stack Verification
"""

from typing import Optional, Dict
from risc201.core.isa import (
    Opcode, DecodedInstruction, decode_instruction, to_signed32, to_unsigned32,
    is_branch_op, is_memory_op, is_multi_cycle_op
)
from risc201.alu.alu import ALU, MultiplierAlgorithm, DividerAlgorithm, DivisionByZeroException
from risc201.core.registers import RegisterFile, CSRFile, CSRCause, CPUException
from risc201.core.memory import Memory
from risc201.core.pmc import PMC
from risc201.pipelines.branch_predictor import BranchPredictor, PredictorMode
from risc201.pipelines.forwarding import HazardUnit

class Latch_IF_ID:
    def __init__(self):
        self.valid: bool = False
        self.pc: int = 0
        self.raw_word: int = 0
        self.pred_taken: bool = False
        self.pred_target: int = 0

    def clear(self):
        self.valid = False
        self.pc = 0
        self.raw_word = 0
        self.pred_taken = False
        self.pred_target = 0


class Latch_ID_RR:
    def __init__(self):
        self.valid: bool = False
        self.pc: int = 0
        self.inst: Optional[DecodedInstruction] = None
        self.pred_taken: bool = False
        self.pred_target: int = 0

    def clear(self):
        self.valid = False
        self.pc = 0
        self.inst = None
        self.pred_taken = False
        self.pred_target = 0


class Latch_RR_EX:
    def __init__(self):
        self.valid: bool = False
        self.pc: int = 0
        self.inst: Optional[DecodedInstruction] = None
        self.valA: int = 0
        self.valB: int = 0
        self.store_val: int = 0
        self.pred_taken: bool = False
        self.pred_target: int = 0

    def clear(self):
        self.valid = False
        self.pc = 0
        self.inst = None
        self.valA = 0
        self.valB = 0
        self.store_val = 0
        self.pred_taken = False
        self.pred_target = 0


class Latch_EX_MEM:
    def __init__(self):
        self.valid: bool = False
        self.pc: int = 0
        self.inst: Optional[DecodedInstruction] = None
        self.alu_result: int = 0
        self.store_val: int = 0

    def clear(self):
        self.valid = False
        self.pc = 0
        self.inst = None
        self.alu_result = 0
        self.store_val = 0


class Latch_MEM_WB:
    def __init__(self):
        self.valid: bool = False
        self.pc: int = 0
        self.inst: Optional[DecodedInstruction] = None
        self.alu_result: int = 0
        self.mem_data: int = 0

    def clear(self):
        self.valid = False
        self.pc = 0
        self.inst = None
        self.alu_result = 0
        self.mem_data = 0


class Processor6Stage:
    """
    6-Stage Pipelined Processor simulation model.
    """
    def __init__(
        self,
        memory: Optional[Memory] = None,
        enable_forwarding: bool = True,
        branch_mode: PredictorMode = PredictorMode.DYNAMIC_2BIT,
        mul_algo: MultiplierAlgorithm = MultiplierAlgorithm.DADDA,
        div_algo: DividerAlgorithm = DividerAlgorithm.SRT
    ):
        self.memory = memory if memory is not None else Memory()
        self.rf = RegisterFile()
        self.csr = CSRFile()
        self.alu = ALU(mul_algo=mul_algo, div_algo=div_algo)
        self.pmc = PMC()
        self.branch_predictor = BranchPredictor(mode=branch_mode)
        self.hazard_unit = HazardUnit(enable_forwarding=enable_forwarding)

        self.pc: int = 0
        self.halted: bool = False
        self.exception_raised: bool = False
        self.last_exception: Optional[CPUException] = None

        # Multi-cycle structural stall counter (for MUL/DIV/MOD latency > 1)
        self.multi_cycle_stall_remaining: int = 0

        # 6-Stage Latches
        self.if_id = Latch_IF_ID()
        self.id_rr = Latch_ID_RR()
        self.rr_ex = Latch_RR_EX()
        self.ex_mem = Latch_EX_MEM()
        self.mem_wb = Latch_MEM_WB()

        self.rf.reset(initial_sp=self.memory.stack_base)

    def reset(self, initial_pc: int = 0):
        self.pc = initial_pc
        self.halted = False
        self.exception_raised = False
        self.last_exception = None
        self.multi_cycle_stall_remaining = 0
        self.rf.reset(initial_sp=self.memory.stack_base)
        self.csr.clear_exception()
        self.pmc.reset()
        self.branch_predictor.reset()
        self.if_id.clear()
        self.id_rr.clear()
        self.rr_ex.clear()
        self.ex_mem.clear()
        self.mem_wb.clear()

    def get_stage_strings(self) -> Dict[str, str]:
        def fmt(inst: Optional[DecodedInstruction], pc: int) -> str:
            if not inst:
                return "NOP (Bubble)"
            return f"0x{pc:04X}: {inst.op_name.upper()} (raw 0x{inst.raw:08X})"

        return {
            "IF": f"Fetching PC=0x{self.pc:04X}" if not self.halted else "HALTED",
            "ID": fmt(decode_instruction(self.if_id.raw_word) if self.if_id.valid else None, self.if_id.pc),
            "RR": fmt(self.id_rr.inst, self.id_rr.pc) if self.id_rr.valid else "NOP (Bubble)",
            "EX": fmt(self.rr_ex.inst, self.rr_ex.pc) if self.rr_ex.valid else "NOP (Bubble)",
            "MEM": fmt(self.ex_mem.inst, self.ex_mem.pc) if self.ex_mem.valid else "NOP (Bubble)",
            "WB": fmt(self.mem_wb.inst, self.mem_wb.pc) if self.mem_wb.valid else "NOP (Bubble)",
        }

    def step(self) -> bool:
        """
        Executes one clock cycle across all 6 pipeline stages.
        """
        if self.halted:
            return False

        self.pmc.tick_cycle()
        self.rf.clear_modified_flags()

        try:
            # Stage 6: Write Back (WB)
            self._stage_wb()

            # Stage 5: Memory Access (MEM)
            next_mem_wb = self._stage_mem()

            # ----------------------------------------------------------------
            # Multi-cycle structural stall handling
            # When EX stage runs a MUL/DIV/MOD with latency > 1, stall
            # IF, ID, and RR for the remaining latency cycles.
            # ----------------------------------------------------------------
            if self.multi_cycle_stall_remaining > 0:
                self.multi_cycle_stall_remaining -= 1
                self.pmc.record_stall(is_load_use=False, is_structural=True)
                self.mem_wb = next_mem_wb
                self.ex_mem.clear()
                return True

            # Stage 4: Execution (EX) - evaluates ALU & resolves branches
            branch_flush, next_ex_mem = self._stage_ex()

            # Detect if EX just started a multi-cycle operation; insert stalls
            if next_ex_mem.valid and next_ex_mem.inst and is_multi_cycle_op(next_ex_mem.inst):
                latency = self.alu.latency_cycles(next_ex_mem.inst.opcode)
                if latency > 1:
                    self.multi_cycle_stall_remaining = latency - 1

            # Stage 3: Register Read (RR) - reads register file and hazards
            stall_pipeline, next_rr_ex = self._stage_rr()

            # Stage 2: Instruction Decode (ID)
            next_id_rr = Latch_ID_RR()
            if not stall_pipeline:
                if self.if_id.valid:
                    next_id_rr.valid = True
                    next_id_rr.pc = self.if_id.pc
                    next_id_rr.inst = decode_instruction(self.if_id.raw_word)
                    next_id_rr.pred_taken = self.if_id.pred_taken
                    next_id_rr.pred_target = self.if_id.pred_target
            else:
                # Keep ID latch intact during stall
                next_id_rr = self.id_rr

            # Stage 1: Instruction Fetch (IF)
            next_if_id = self.if_id
            if branch_flush:
                # Flush IF, ID, RR on branch misprediction
                self.if_id.clear()
                self.id_rr.clear()
                next_rr_ex.clear()
                next_id_rr.clear()
            elif not stall_pipeline:
                next_if_id = self._stage_if()
            else:
                self.pmc.record_stall(is_load_use=True)

            # Advance latches
            self.mem_wb = next_mem_wb
            self.ex_mem = next_ex_mem
            if branch_flush:
                self.if_id.clear()
                self.id_rr.clear()
                self.rr_ex.clear()
            else:
                self.rr_ex = next_rr_ex
                self.id_rr = next_id_rr
                if not stall_pipeline:
                    self.if_id = next_if_id

        except CPUException as e:
            self.exception_raised = True
            self.last_exception = e
            self.halted = True
            self.csr.trigger_exception(e.cause, e.pc, e.badvaddr)
            return False

        if (not self.if_id.valid and not self.id_rr.valid and not self.rr_ex.valid
            and not self.ex_mem.valid and not self.mem_wb.valid and self.halted):
            return False

        return True

    def _stage_wb(self):
        """Write Back stage: commits results to Register File."""
        if not self.mem_wb.valid or not self.mem_wb.inst:
            return

        inst = self.mem_wb.inst
        if inst.opcode == Opcode.HLT:
            self.halted = True
            self.pmc.commit_instruction()
            return

        if inst.writes_rf:
            wb_val = self.mem_wb.mem_data if inst.opcode == Opcode.LD else self.mem_wb.alu_result
            self.rf.write(inst.dest_reg, wb_val)

        self.memory.check_stack_safety(self.rf.sp, self.mem_wb.pc)
        self.pmc.commit_instruction()

    def _stage_mem(self) -> Latch_MEM_WB:
        """Memory Access stage."""
        out = Latch_MEM_WB()
        if not self.ex_mem.valid or not self.ex_mem.inst:
            return out

        inst = self.ex_mem.inst
        pc = self.ex_mem.pc
        alu_res = self.ex_mem.alu_result
        mem_data = 0

        if inst.opcode == Opcode.LD:
            mem_data = self.memory.read_word(alu_res, pc)
        elif inst.opcode == Opcode.ST:
            store_val = self.ex_mem.store_val
            # MEM-to-MEM forwarding for store after load
            if (self.hazard_unit.enable_forwarding and self.mem_wb.valid and
                self.mem_wb.inst and self.mem_wb.inst.opcode == Opcode.LD and
                self.mem_wb.inst.dest_reg == inst.rd and inst.rd != 0):
                store_val = self.mem_wb.mem_data
                self.pmc.record_forwarding()
            self.memory.write_word(alu_res, store_val, pc)

        out.valid = True
        out.pc = pc
        out.inst = inst
        out.alu_result = alu_res
        out.mem_data = mem_data
        return out

    def _stage_ex(self):
        """Execute stage: ALU calculations & Branch resolution."""
        out = Latch_EX_MEM()
        branch_flush = False
        if not self.rr_ex.valid or not self.rr_ex.inst:
            return branch_flush, out

        inst = self.rr_ex.inst
        pc = self.rr_ex.pc
        valA = self.rr_ex.valA
        valB = self.rr_ex.valB
        store_val = self.rr_ex.store_val

        # Multiplexer Forwarding Network at ALU Inputs
        if self.hazard_unit.enable_forwarding:
            # Forwarding for Operand A (rs1)
            if inst.reads_rs1 and inst.rs1 != 0:
                if self.ex_mem.valid and self.ex_mem.inst and self.ex_mem.inst.writes_rf and self.ex_mem.inst.dest_reg == inst.rs1:
                    valA = self.ex_mem.alu_result
                    self.pmc.record_forwarding()
                elif self.mem_wb.valid and self.mem_wb.inst and self.mem_wb.inst.writes_rf and self.mem_wb.inst.dest_reg == inst.rs1:
                    valA = self.mem_wb.mem_data if self.mem_wb.inst.opcode == Opcode.LD else self.mem_wb.alu_result
                    self.pmc.record_forwarding()
                else:
                    # Fallback to updated Register File (e.g. following multi-cycle stalls)
                    valA = self.rf.read(inst.rs1)

            # Forwarding for Operand B (rs2 or rs1 for reg MOV)
            if inst.opcode == Opcode.MOV and not inst.is_imm and inst.rs1 != 0:
                if self.ex_mem.valid and self.ex_mem.inst and self.ex_mem.inst.writes_rf and self.ex_mem.inst.dest_reg == inst.rs1:
                    valB = self.ex_mem.alu_result
                    self.pmc.record_forwarding()
                elif self.mem_wb.valid and self.mem_wb.inst and self.mem_wb.inst.writes_rf and self.mem_wb.inst.dest_reg == inst.rs1:
                    valB = self.mem_wb.mem_data if self.mem_wb.inst.opcode == Opcode.LD else self.mem_wb.alu_result
                    self.pmc.record_forwarding()
                else:
                    valB = self.rf.read(inst.rs1)
            elif not inst.is_imm and inst.reads_rs2 and inst.rs2 != 0:
                if self.ex_mem.valid and self.ex_mem.inst and self.ex_mem.inst.writes_rf and self.ex_mem.inst.dest_reg == inst.rs2:
                    valB = self.ex_mem.alu_result
                    self.pmc.record_forwarding()
                elif self.mem_wb.valid and self.mem_wb.inst and self.mem_wb.inst.writes_rf and self.mem_wb.inst.dest_reg == inst.rs2:
                    valB = self.mem_wb.mem_data if self.mem_wb.inst.opcode == Opcode.LD else self.mem_wb.alu_result
                    self.pmc.record_forwarding()
                else:
                    valB = self.rf.read(inst.rs2)

            # Forwarding for store value (rd) in ST instruction
            if inst.opcode == Opcode.ST and inst.rd != 0:
                if self.ex_mem.valid and self.ex_mem.inst and self.ex_mem.inst.writes_rf and self.ex_mem.inst.dest_reg == inst.rd:
                    store_val = self.ex_mem.alu_result
                    self.pmc.record_forwarding()
                elif self.mem_wb.valid and self.mem_wb.inst and self.mem_wb.inst.writes_rf and self.mem_wb.inst.dest_reg == inst.rd:
                    store_val = self.mem_wb.mem_data if self.mem_wb.inst.opcode == Opcode.LD else self.mem_wb.alu_result
                    self.pmc.record_forwarding()
                else:
                    store_val = self.rf.read(inst.rd)

        alu_res = 0

        # Trap handling
        if inst.opcode == Opcode.TRAP:
            cause_code = CSRCause(inst.trap_id) if inst.trap_id in CSRCause._value2member_map_ else CSRCause.TRAP_CALL
            raise CPUException(cause_code, pc, f"TRAP triggered with code {inst.trap_id}")

        if inst.opcode == Opcode.CALL:
            alu_res = pc + 4
        elif is_memory_op(inst):
            alu_res = to_signed32(valA + inst.imm)
        elif inst.opcode != Opcode.NOP and inst.opcode != Opcode.HLT and not is_branch_op(inst.opcode):
            try:
                alu_res = self.alu.execute(inst.opcode, valA, valB, update_flags=True)
            except DivisionByZeroException:
                raise CPUException(CSRCause.DIVISION_BY_ZERO, pc, "Division by zero encountered in ALU")

        # Branch resolution in EX stage
        if is_branch_op(inst.opcode):
            actual_taken = False
            actual_target = pc + 4

            if inst.opcode == Opcode.B:
                actual_taken = True
                actual_target = pc + (inst.offset * 4)
            elif inst.opcode == Opcode.CALL:
                actual_taken = True
                actual_target = pc + (inst.offset * 4)
            elif inst.opcode == Opcode.RET:
                actual_taken = True
                actual_target = self.rf.ra
            elif inst.opcode == Opcode.BEQ:
                actual_taken = self.alu.flags.Z
                actual_target = pc + (inst.offset * 4)
            elif inst.opcode == Opcode.BNE:
                actual_taken = not self.alu.flags.Z
                actual_target = pc + (inst.offset * 4)
            elif inst.opcode == Opcode.BGT:
                actual_taken = not self.alu.flags.Z and (self.alu.flags.N == self.alu.flags.V)
                actual_target = pc + (inst.offset * 4)
            elif inst.opcode == Opcode.BLT:
                actual_taken = (self.alu.flags.N != self.alu.flags.V)
                actual_target = pc + (inst.offset * 4)

            pred_taken = self.rr_ex.pred_taken
            pred_target = self.rr_ex.pred_target
            mispredicted = (actual_taken != pred_taken) or (actual_taken and pred_target != actual_target)

            self.pmc.record_branch(mispredicted=mispredicted)
            self.branch_predictor.update(pc, inst.opcode, actual_taken, actual_target)

            if mispredicted:
                self.pc = actual_target if actual_taken else (pc + 4)
                branch_flush = True

        out.valid = True
        out.pc = pc
        out.inst = inst
        out.alu_result = alu_res
        out.store_val = store_val
        return branch_flush, out

    def _stage_rr(self):
        """Register Read / Operand Fetch stage & Hazard Detection."""
        out = Latch_RR_EX()
        if not self.id_rr.valid or not self.id_rr.inst:
            return False, out

        inst = self.id_rr.inst
        pc = self.id_rr.pc

        # 1. Load-Use Hazard check against RR/EX
        ex_inst = self.rr_ex.inst if self.rr_ex.valid else None
        if self.hazard_unit.check_load_use_hazard(inst, ex_inst):
            return True, out

        # 2. RAW Hazard check when forwarding is disabled
        if not self.hazard_unit.enable_forwarding:
            mem_inst = self.ex_mem.inst if self.ex_mem.valid else None
            if self.hazard_unit.check_raw_hazard_without_forwarding(inst, ex_inst, mem_inst):
                self.pmc.record_stall(is_load_use=False)
                return True, out

        # 3. Read registers
        valA = self.rf.read(inst.rs1)
        store_val = 0
        if inst.opcode == Opcode.ST:
            valB = 0
            store_val = self.rf.read(inst.rd)
        elif inst.is_imm:
            valB = inst.imm
        elif inst.opcode == Opcode.MOV:
            valB = self.rf.read(inst.rs1)
        else:
            valB = self.rf.read(inst.rs2)

        # Write-to-Read Register File bypass
        if self.mem_wb.valid and self.mem_wb.inst and self.mem_wb.inst.writes_rf:
            wb_reg = self.mem_wb.inst.dest_reg
            wb_val = self.mem_wb.mem_data if self.mem_wb.inst.opcode == Opcode.LD else self.mem_wb.alu_result
            if wb_reg != 0:
                if inst.reads_rs1 and inst.rs1 == wb_reg:
                    valA = wb_val
                if inst.opcode == Opcode.MOV and not inst.is_imm and inst.rs1 == wb_reg:
                    valB = wb_val
                elif not inst.is_imm and inst.reads_rs2 and inst.rs2 == wb_reg:
                    valB = wb_val
                if inst.opcode == Opcode.ST and inst.rd == wb_reg:
                    store_val = wb_val

        out.valid = True
        out.pc = pc
        out.inst = inst
        out.valA = valA
        out.valB = valB
        out.store_val = store_val
        out.pred_taken = self.id_rr.pred_taken
        out.pred_target = self.id_rr.pred_target
        return False, out

    def _stage_if(self) -> Latch_IF_ID:
        """Instruction Fetch stage."""
        out = Latch_IF_ID()
        if self.halted or self.pc >= self.memory.size or self.pc < 0:
            return out

        if self.if_id.valid and (self.if_id.raw_word >> 27) == Opcode.HLT.value:
            return out
        if self.id_rr.valid and self.id_rr.inst and self.id_rr.inst.opcode == Opcode.HLT:
            return out
        if self.rr_ex.valid and self.rr_ex.inst and self.rr_ex.inst.opcode == Opcode.HLT:
            return out
        if self.ex_mem.valid and self.ex_mem.inst and self.ex_mem.inst.opcode == Opcode.HLT:
            return out

        raw = self.memory.read_word(self.pc, self.pc)
        inst = decode_instruction(raw)

        pred_taken, pred_target = self.branch_predictor.predict(self.pc, inst.opcode, self.pc + 4)

        out.valid = True
        out.pc = self.pc
        out.raw_word = raw
        out.pred_taken = pred_taken
        out.pred_target = pred_target

        if pred_taken:
            self.pc = pred_target
        else:
            self.pc += 4

        return out

    def run(self, max_cycles: int = 100000) -> bool:
        cycles = 0
        while not self.halted and cycles < max_cycles:
            cycles += 1
            if not self.step():
                break
        return self.halted
