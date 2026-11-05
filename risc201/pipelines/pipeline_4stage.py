"""
RISC201 4-Stage Pipelined Processor
Stages:
  1. IF     : Instruction Fetch
  2. ID/OF  : Instruction Decode & Operand Fetch
  3. EX/MEM : Execute ALU & Memory Access
  4. WB     : Write Back

Features:
- Hardwired Zero Register (r0)
- Full-Matrix Data Forwarding (EX-to-EX, WB-to-EX)
- Dynamic 2-bit Saturating Counter Branch Predictor with BTB
- Hardware Performance Monitoring Counters (PMCs)
- CSR Exception Trapping (Division by zero, misaligned access, canary corrupted, etc.)
- Structural Stalling for multi-cycle ALU operations (Dadda MUL, SRT DIV/MOD)
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
from risc201.pipelines.forwarding import HazardUnit, ForwardSource

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


class Latch_ID_EX:
    def __init__(self):
        self.valid: bool = False
        self.pc: int = 0
        self.inst: Optional[DecodedInstruction] = None
        self.valA: int = 0
        self.valB: int = 0
        self.pred_taken: bool = False
        self.pred_target: int = 0

    def clear(self):
        self.valid = False
        self.pc = 0
        self.inst = None
        self.valA = 0
        self.valB = 0
        self.pred_taken = False
        self.pred_target = 0


class Latch_EX_WB:
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


class Processor4Stage:
    """
    4-Stage Pipelined Processor simulation model.
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

        # Pipeline latches
        self.if_id = Latch_IF_ID()
        self.id_ex = Latch_ID_EX()
        self.ex_wb = Latch_EX_WB()

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
        self.id_ex.clear()
        self.ex_wb.clear()

    def get_stage_strings(self) -> Dict[str, str]:
        def fmt(inst: Optional[DecodedInstruction], pc: int) -> str:
            if not inst:
                return "NOP (Bubble)"
            return f"0x{pc:04X}: {inst.op_name.upper()} (raw 0x{inst.raw:08X})"

        return {
            "IF": f"Fetching PC=0x{self.pc:04X}" if not self.halted else "HALTED",
            "ID/OF": fmt(decode_instruction(self.if_id.raw_word) if self.if_id.valid else None, self.if_id.pc),
            "EX/MEM": fmt(self.id_ex.inst, self.id_ex.pc) if self.id_ex.valid else "NOP (Bubble)",
            "WB": fmt(self.ex_wb.inst, self.ex_wb.pc) if self.ex_wb.valid else "NOP (Bubble)",
        }

    def step(self) -> bool:
        """
        Executes one clock cycle across all 4 pipeline stages.
        Returns True if execution can continue, False if halted or faulted.
        """
        if self.halted:
            return False

        self.pmc.tick_cycle()
        self.rf.clear_modified_flags()

        try:
            # Stage 4: Write Back (WB)
            self._stage_wb()

            # ----------------------------------------------------------------
            # Multi-cycle structural stall handling
            # If a multi-cycle ALU operation (MUL / DIV / MOD) is in EX, we
            # stall IF, ID and suppress latch advancement until the remaining
            # latency cycles drain to zero.
            # ----------------------------------------------------------------
            if self.multi_cycle_stall_remaining > 0:
                self.multi_cycle_stall_remaining -= 1
                self.pmc.record_stall(is_load_use=False, is_structural=True)
                # Keep EX/WB latch clear so it doesn't repeatedly commit
                self.ex_wb.clear()
                return True

            # Stage 3: Execute & Memory (EX/MEM)
            next_ex_wb = self._stage_ex_mem()

            # Detect if EX just started a multi-cycle operation; insert stalls
            if next_ex_wb.valid and next_ex_wb.inst and is_multi_cycle_op(next_ex_wb.inst):
                latency = self.alu.latency_cycles(next_ex_wb.inst.opcode)
                if latency > 1:
                    self.multi_cycle_stall_remaining = latency - 1

            # Stage 2: Instruction Decode & Operand Fetch (ID/OF)
            stall_id, flush_if, next_id_ex = self._stage_id_of(next_ex_wb)

            # Stage 1: Instruction Fetch (IF)
            if not stall_id:
                next_if_id = self._stage_if(flush=flush_if)
                self.if_id = next_if_id
            else:
                self.pmc.record_stall(is_load_use=True)

            # Advance latches
            self.ex_wb = next_ex_wb
            self.id_ex = next_id_ex

        except CPUException as e:
            self.exception_raised = True
            self.last_exception = e
            self.halted = True
            self.csr.trigger_exception(e.cause, e.pc, e.badvaddr)
            return False

        # Termination check: all latches empty and halted
        if not self.if_id.valid and not self.id_ex.valid and not self.ex_wb.valid and self.halted:
            return False

        return True

    def _stage_wb(self):
        """Write Back stage: commit results to Register File."""
        if not self.ex_wb.valid or not self.ex_wb.inst:
            return

        inst = self.ex_wb.inst
        if inst.opcode == Opcode.HLT:
            self.halted = True
            self.pmc.commit_instruction()
            return

        if inst.writes_rf:
            wb_val = self.ex_wb.mem_data if inst.opcode == Opcode.LD else self.ex_wb.alu_result
            dest = inst.dest_reg
            # Hardwired r0: writing to r0 is ignored inside RegisterFile.write()
            self.rf.write(dest, wb_val)

        # Check stack safety against current SP
        self.memory.check_stack_safety(self.rf.sp, self.ex_wb.pc)
        self.pmc.commit_instruction()

    def _stage_ex_mem(self) -> Latch_EX_WB:
        """Execute & Memory stage: runs ALU and Memory read/write."""
        out = Latch_EX_WB()
        if not self.id_ex.valid or not self.id_ex.inst:
            return out

        inst = self.id_ex.inst
        pc = self.id_ex.pc
        valA = self.id_ex.valA
        valB = self.id_ex.valB

        # Forwarding from previous instruction (now in ex_wb)
        if self.hazard_unit.enable_forwarding:
            if self.ex_wb.valid and self.ex_wb.inst and self.ex_wb.inst.writes_rf and self.ex_wb.inst.dest_reg != 0:
                fwd_val = self.ex_wb.mem_data if self.ex_wb.inst.opcode == Opcode.LD else self.ex_wb.alu_result
                if inst.reads_rs1 and self.ex_wb.inst.dest_reg == inst.rs1:
                    valA = fwd_val
                    self.pmc.record_forwarding()
                if inst.opcode == Opcode.MOV and not inst.is_imm and self.ex_wb.inst.dest_reg == inst.rs1:
                    valB = fwd_val
                    self.pmc.record_forwarding()
                elif not inst.is_imm and inst.reads_rs2 and self.ex_wb.inst.dest_reg == inst.rs2:
                    valB = fwd_val
                    self.pmc.record_forwarding()
                if inst.opcode == Opcode.ST and self.ex_wb.inst.dest_reg == inst.rd:
                    valB = fwd_val
                    self.pmc.record_forwarding()

        alu_res = 0
        mem_data = 0

        # Trap handling
        if inst.opcode == Opcode.TRAP:
            cause_code = CSRCause(inst.trap_id) if inst.trap_id in CSRCause._value2member_map_ else CSRCause.TRAP_CALL
            raise CPUException(cause_code, pc, f"TRAP triggered with code {inst.trap_id}")

        if inst.opcode == Opcode.CALL:
            alu_res = pc + 4  # Return address saved into r15
        elif is_memory_op(inst):
            # Address = rs1 + imm
            addr = to_signed32(valA + inst.imm)
            alu_res = addr
            if inst.opcode == Opcode.LD:
                mem_data = self.memory.read_word(addr, pc)
            elif inst.opcode == Opcode.ST:
                # Store valB (which holds rd value) into memory
                self.memory.write_word(addr, valB, pc)
        elif inst.opcode != Opcode.NOP and inst.opcode != Opcode.HLT and not is_branch_op(inst.opcode):
            try:
                alu_res = self.alu.execute(inst.opcode, valA, valB, update_flags=True)
            except DivisionByZeroException:
                raise CPUException(CSRCause.DIVISION_BY_ZERO, pc, "Division by zero encountered in ALU")

        out.valid = True
        out.pc = pc
        out.inst = inst
        out.alu_result = alu_res
        out.mem_data = mem_data
        return out

    def _stage_id_of(self, next_ex_wb: Latch_EX_WB):
        """Decode instruction, fetch operands, resolve branches, detect hazards."""
        out = Latch_ID_EX()
        if not self.if_id.valid:
            return False, False, out

        inst = decode_instruction(self.if_id.raw_word)
        pc = self.if_id.pc

        # 1. Hazard Detection
        # Check load-use hazard with EX/MEM stage
        if self.hazard_unit.check_load_use_hazard(inst, self.id_ex.inst):
            # Stall: do not advance IF/ID, insert bubble into ID/EX
            return True, False, out

        # If forwarding is disabled, check RAW hazards against both stages
        if not self.hazard_unit.enable_forwarding:
            ex_inst = self.id_ex.inst if self.id_ex.valid else None
            wb_inst = self.ex_wb.inst if self.ex_wb.valid else None
            if self.hazard_unit.check_raw_hazard_without_forwarding(inst, ex_inst, wb_inst):
                self.pmc.record_stall(is_load_use=False)
                return True, False, out

        # 2. Read Operands with Forwarding Multiplexer
        # Operand A (rs1)
        valA = self.rf.read(inst.rs1)

        # Operand B (rs2 or imm or rs1 for reg mov)
        if inst.opcode == Opcode.ST:
            valB = self.rf.read(inst.rd)
        elif inst.is_imm:
            valB = inst.imm
        elif inst.opcode == Opcode.MOV:
            valB = self.rf.read(inst.rs1)
        else:
            valB = self.rf.read(inst.rs2)

        # Forward from stage just evaluated in this cycle (next_ex_wb)
        if self.hazard_unit.enable_forwarding and next_ex_wb.valid and next_ex_wb.inst and next_ex_wb.inst.writes_rf:
            fwd_dest = next_ex_wb.inst.dest_reg
            if fwd_dest != 0:
                fwd_val = next_ex_wb.mem_data if next_ex_wb.inst.opcode == Opcode.LD else next_ex_wb.alu_result
                if inst.reads_rs1 and fwd_dest == inst.rs1:
                    valA = fwd_val
                    self.pmc.record_forwarding()
                if inst.opcode == Opcode.ST and fwd_dest == inst.rd:
                    valB = fwd_val
                    self.pmc.record_forwarding()
                elif inst.opcode == Opcode.MOV and not inst.is_imm and fwd_dest == inst.rs1:
                    valB = fwd_val
                    self.pmc.record_forwarding()
                elif not inst.is_imm and inst.reads_rs2 and fwd_dest == inst.rs2:
                    valB = fwd_val
                    self.pmc.record_forwarding()

        # Forward from ex_wb in case RF write hasn't propagated yet
        if self.hazard_unit.enable_forwarding and self.ex_wb.valid and self.ex_wb.inst and self.ex_wb.inst.writes_rf:
            fwd_dest = self.ex_wb.inst.dest_reg
            if fwd_dest != 0:
                fwd_val = self.ex_wb.mem_data if self.ex_wb.inst.opcode == Opcode.LD else self.ex_wb.alu_result
                if inst.reads_rs1 and fwd_dest == inst.rs1:
                    valA = fwd_val
                    self.pmc.record_forwarding()
                if inst.opcode == Opcode.ST and fwd_dest == inst.rd:
                    valB = fwd_val
                    self.pmc.record_forwarding()
                elif inst.opcode == Opcode.MOV and not inst.is_imm and fwd_dest == inst.rs1:
                    valB = fwd_val
                    self.pmc.record_forwarding()
                elif not inst.is_imm and inst.reads_rs2 and fwd_dest == inst.rs2:
                    valB = fwd_val
                    self.pmc.record_forwarding()

        # 3. Branch Evaluation (in ID/OF stage in 4-stage pipeline)
        flush_if = False
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

            # Check if prediction matched actual outcome
            pred_taken = self.if_id.pred_taken
            pred_target = self.if_id.pred_target
            mispredicted = (actual_taken != pred_taken) or (actual_taken and pred_target != actual_target)

            self.pmc.record_branch(mispredicted=mispredicted)
            self.branch_predictor.update(pc, inst.opcode, actual_taken, actual_target)

            if mispredicted:
                # Misprediction penalty: redirect PC and flush IF stage
                self.pc = actual_target if actual_taken else (pc + 4)
                flush_if = True

        out.valid = True
        out.pc = pc
        out.inst = inst
        out.valA = valA
        out.valB = valB
        return False, flush_if, out

    def _stage_if(self, flush: bool = False) -> Latch_IF_ID:
        """Instruction Fetch stage."""
        out = Latch_IF_ID()
        if flush or self.halted:
            return out

        if self.if_id.valid and (self.if_id.raw_word >> 27) == Opcode.HLT.value:
            return out
        if self.id_ex.valid and self.id_ex.inst and self.id_ex.inst.opcode == Opcode.HLT:
            return out
        if self.ex_wb.valid and self.ex_wb.inst and self.ex_wb.inst.opcode == Opcode.HLT:
            return out

        if self.pc >= self.memory.size or self.pc < 0:
            return out

        raw = self.memory.read_word(self.pc, self.pc)
        inst = decode_instruction(raw)

        # Predict next PC using dynamic branch predictor
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
        """Run until halt or max cycles."""
        cycles = 0
        while not self.halted and cycles < max_cycles:
            cycles += 1
            if not self.step():
                break
        return self.halted
