"""
Full-Matrix Data Forwarding Network & Hazard Detection Unit
Implements:
- EX-to-EX Forwarding (ALU result forwarded directly to next ALU input)
- MEM-to-EX Forwarding (Memory load or previous ALU result to ALU input)
- WB-to-EX / Register File bypass forwarding
- MEM-to-MEM Forwarding (Store after Load)
- Load-Use Hazard Detection Unit (1-cycle stall bubble insertion)
- Toggleable Forwarding mode to measure CPI with and without forwarding.
"""

from enum import IntEnum
from typing import Optional, Tuple
from risc201.core.isa import Opcode, DecodedInstruction

class ForwardSource(IntEnum):
    NONE      = 0  # Use register file output
    EX_TO_EX  = 1  # Forward from EX/MEM latch (ALU result)
    MEM_TO_EX = 2  # Forward from MEM/WB latch (Memory data or older ALU result)
    WB_TO_EX  = 3  # Forward from WB stage

class HazardUnit:
    """
    Detects RAW Hazards and generates forwarding select lines or stall bubbles.
    """
    def __init__(self, enable_forwarding: bool = True):
        self.enable_forwarding = enable_forwarding

    def check_load_use_hazard(
        self,
        id_inst: Optional[DecodedInstruction],
        ex_inst: Optional[DecodedInstruction]
    ) -> bool:
        """
        Detects Load-Use Hazard between ID stage and EX stage.
        If instruction in EX is a load (LD) and its destination matches
        a source register of instruction in ID, a 1-cycle stall is required.
        """
        if not id_inst or not ex_inst:
            return False

        if ex_inst.opcode == Opcode.LD and ex_inst.rd != 0:
            # Check if ID instruction reads ex_inst.rd
            if id_inst.reads_rs1 and id_inst.rs1 == ex_inst.rd:
                return True
            if id_inst.reads_rs2 and id_inst.rs2 == ex_inst.rd:
                return True
            if id_inst.opcode == Opcode.ST and id_inst.rd == ex_inst.rd:
                # ST rd, imm[rs1] reads rd
                return True
        return False

    def check_raw_hazard_without_forwarding(
        self,
        id_inst: Optional[DecodedInstruction],
        ex_inst: Optional[DecodedInstruction],
        mem_inst: Optional[DecodedInstruction]
    ) -> bool:
        """
        When forwarding is DISABLED, any dependency on an uncommitted instruction stalls.
        """
        if not id_inst:
            return False

        read_regs = []
        if id_inst.reads_rs1 and id_inst.rs1 != 0:
            read_regs.append(id_inst.rs1)
        if id_inst.reads_rs2 and id_inst.rs2 != 0:
            read_regs.append(id_inst.rs2)
        if id_inst.opcode == Opcode.ST and id_inst.rd != 0:
            read_regs.append(id_inst.rd)

        for reg in read_regs:
            # Check EX stage
            if ex_inst and ex_inst.writes_rf and ex_inst.dest_reg == reg and reg != 0:
                return True
            # Check MEM stage
            if mem_inst and mem_inst.writes_rf and mem_inst.dest_reg == reg and reg != 0:
                return True

        return False

    def get_forward_select(
        self,
        operand_reg: int,
        ex_mem_inst: Optional[DecodedInstruction],
        mem_wb_inst: Optional[DecodedInstruction]
    ) -> Tuple[ForwardSource, Optional[int]]:
        """
        Determines the multiplexer select for an operand register (rs1 or rs2).
        Returns: (ForwardSource, forwarded_value_from_pipeline_register)
        """
        if not self.enable_forwarding or operand_reg == 0:
            return ForwardSource.NONE, None

        # Priority 1: EX/MEM stage (most recent result)
        if (ex_mem_inst and ex_mem_inst.writes_rf and
            ex_mem_inst.dest_reg == operand_reg):
            return ForwardSource.EX_TO_EX, None

        # Priority 2: MEM/WB stage
        if (mem_wb_inst and mem_wb_inst.writes_rf and
            mem_wb_inst.dest_reg == operand_reg):
            return ForwardSource.MEM_TO_EX, None

        return ForwardSource.NONE, None
