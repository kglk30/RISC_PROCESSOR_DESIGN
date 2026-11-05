"""
Microprogrammed Control Unit for RISC201
Implements:
1. Control Store ROM (Microcode Memory)
2. Micro-Program Counter (uPC) and Micro-Instruction Register (uIR)
3. Both Horizontal (wide unencoded) and Vertical (narrow encoded) Microprogramming models
4. Opcode Dispatch Table and Micro-sequencing logic
5. Cycle-by-cycle micro-step execution with CLI inspection
"""

from enum import IntEnum, Enum
from typing import Dict, List, Optional, Tuple, NamedTuple
from risc201.core.isa import Opcode, DecodedInstruction, decode_instruction, to_signed32, is_branch_op, is_memory_op
from risc201.core.registers import RegisterFile, CSRFile, CSRCause, CPUException
from risc201.core.memory import Memory
from risc201.alu.alu import ALU, DivisionByZeroException
from risc201.core.pmc import PMC

class MicroSeqOp(IntEnum):
    NEXT = 0        # uPC = uPC + 1
    DISPATCH = 1    # uPC = DispatchTable[opcode]
    FETCH = 2       # uPC = 0 (Start of next instruction fetch)
    JUMP = 3        # uPC = target specified in microinstruction
    BRANCH_COND = 4 # uPC = target if condition flag holds, else uPC + 1

class HorizontalMicrocode(NamedTuple):
    """
    Wide unencoded control word (28 bits total).
    Direct bit signals driving datapath control lines.
    """
    pc_write: bool
    pc_src: int         # 0=PC+4, 1=ALU/Branch target, 2=Return address
    mem_read: bool
    mem_write: bool
    mem_to_reg: bool
    ir_write: bool
    reg_write: bool
    alu_srcA: int       # 0=rs1, 1=PC, 2=SP
    alu_srcB: int       # 0=rs2, 1=imm, 2=const 4, 3=const 0
    alu_op: int         # Opcode
    seq_op: MicroSeqOp
    next_uaddr: int
    name: str

class VerticalMicrocode(NamedTuple):
    """
    Compact encoded microinstruction (14 bits total).
    Decoded via micro-decoders into datapath signals.
    """
    alu_func: int       # 4 bits (ALU operation)
    src_sel: int        # 2 bits (Source operand selection)
    dst_sel: int        # 2 bits (Destination selection)
    mem_ctrl: int       # 2 bits (0: None, 1: Read, 2: Write)
    reg_write: bool     # 1 bit
    seq_ctrl: MicroSeqOp# 3 bits
    next_uaddr: int     # 6 bits
    name: str


class ControlStore:
    """
    Control Memory holding micro-routines for each RISC201 instruction.
    Addresses:
      0..1   : Instruction Fetch & Decode
      10..12 : ADD micro-sequence
      14..16 : SUB micro-sequence
      18..20 : MUL micro-sequence
      22..24 : DIV micro-sequence
      26..28 : AND / OR / NOT micro-sequence
      30..33 : LD (Load) micro-sequence
      35..38 : ST (Store) micro-sequence
      40..42 : BEQ micro-sequence
      44..46 : B (Unconditional Branch)
      48..51 : CALL micro-sequence
      52..54 : RET micro-sequence
      60..61 : HLT micro-sequence
    """
    def __init__(self):
        self.horizontal_rom: Dict[int, HorizontalMicrocode] = {}
        self.vertical_rom: Dict[int, VerticalMicrocode] = {}
        self.dispatch_table: Dict[int, int] = {}
        self._build_microcode()

    def _build_microcode(self):
        # 1. Fetch Routine (uPC 0 and 1)
        # uPC 0: MAR <- PC, PC <- PC + 4, Read Memory
        self.horizontal_rom[0] = HorizontalMicrocode(
            pc_write=True, pc_src=0, mem_read=True, mem_write=False,
            mem_to_reg=False, ir_write=True, reg_write=False,
            alu_srcA=1, alu_srcB=2, alu_op=Opcode.ADD, seq_op=MicroSeqOp.NEXT,
            next_uaddr=1, name="FETCH_READ"
        )
        self.vertical_rom[0] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=1, dst_sel=0, mem_ctrl=1,
            reg_write=False, seq_ctrl=MicroSeqOp.NEXT, next_uaddr=1, name="FETCH_READ"
        )

        # uPC 1: Decode & Dispatch to Opcode Routine
        self.horizontal_rom[1] = HorizontalMicrocode(
            pc_write=False, pc_src=0, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=0, alu_srcB=0, alu_op=Opcode.NOP, seq_op=MicroSeqOp.DISPATCH,
            next_uaddr=0, name="DISPATCH"
        )
        self.vertical_rom[1] = VerticalMicrocode(
            alu_func=Opcode.NOP, src_sel=0, dst_sel=0, mem_ctrl=0,
            reg_write=False, seq_ctrl=MicroSeqOp.DISPATCH, next_uaddr=0, name="DISPATCH"
        )

        # Build micro-sequences for operations
        routines = [
            (Opcode.ADD,    10, "ADD"),
            (Opcode.SUB,    14, "SUB"),
            (Opcode.MUL,    18, "MUL"),
            (Opcode.DIV,    22, "DIV"),
            (Opcode.MOD,    24, "MOD"),
            (Opcode.CMP,    26, "CMP"),
            (Opcode.AND,    28, "AND"),
            (Opcode.OR,     30, "OR"),
            (Opcode.NOT,    32, "NOT"),
            (Opcode.MOV,    34, "MOV"),
            (Opcode.LSL,    36, "LSL"),
            (Opcode.LSR,    38, "LSR"),
            (Opcode.ASR,    40, "ASR"),
            (Opcode.CLZ,    42, "CLZ"),    # NEW: Count Leading Zeros
            (Opcode.POPCNT, 44, "POPCNT"), # NEW: Population Count
        ]

        for op, addr, name in routines:
            self.dispatch_table[op] = addr
            # Step 1: ALU Compute
            self.horizontal_rom[addr] = HorizontalMicrocode(
                pc_write=False, pc_src=0, mem_read=False, mem_write=False,
                mem_to_reg=False, ir_write=False, reg_write=(op != Opcode.CMP),
                alu_srcA=0, alu_srcB=0, alu_op=op, seq_op=MicroSeqOp.FETCH,
                next_uaddr=0, name=f"{name}_EXEC_WB"
            )
            self.vertical_rom[addr] = VerticalMicrocode(
                alu_func=op, src_sel=0, dst_sel=0, mem_ctrl=0,
                reg_write=(op != Opcode.CMP), seq_ctrl=MicroSeqOp.FETCH,
                next_uaddr=0, name=f"{name}_EXEC_WB"
            )

        # LD (Load): uPC 50, 51
        self.dispatch_table[Opcode.LD] = 50
        # uPC 50: Compute Effective Address = rs1 + imm
        self.horizontal_rom[50] = HorizontalMicrocode(
            pc_write=False, pc_src=0, mem_read=True, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=0, alu_srcB=1, alu_op=Opcode.ADD, seq_op=MicroSeqOp.NEXT,
            next_uaddr=51, name="LD_ADDR_CALC"
        )
        self.vertical_rom[50] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=0, dst_sel=1, mem_ctrl=1,
            reg_write=False, seq_ctrl=MicroSeqOp.NEXT, next_uaddr=51, name="LD_ADDR_CALC"
        )
        # uPC 51: Read Memory Data and Write to rd
        self.horizontal_rom[51] = HorizontalMicrocode(
            pc_write=False, pc_src=0, mem_read=False, mem_write=False,
            mem_to_reg=True, ir_write=False, reg_write=True,
            alu_srcA=0, alu_srcB=0, alu_op=Opcode.NOP, seq_op=MicroSeqOp.FETCH,
            next_uaddr=0, name="LD_MEM_WB"
        )
        self.vertical_rom[51] = VerticalMicrocode(
            alu_func=Opcode.NOP, src_sel=0, dst_sel=0, mem_ctrl=0,
            reg_write=True, seq_ctrl=MicroSeqOp.FETCH, next_uaddr=0, name="LD_MEM_WB"
        )

        # ST (Store): uPC 54
        self.dispatch_table[Opcode.ST] = 54
        self.horizontal_rom[54] = HorizontalMicrocode(
            pc_write=False, pc_src=0, mem_read=False, mem_write=True,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=0, alu_srcB=1, alu_op=Opcode.ADD, seq_op=MicroSeqOp.FETCH,
            next_uaddr=0, name="ST_MEM_WRITE"
        )
        self.vertical_rom[54] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=0, dst_sel=2, mem_ctrl=2,
            reg_write=False, seq_ctrl=MicroSeqOp.FETCH, next_uaddr=0, name="ST_MEM_WRITE"
        )

        # BEQ: uPC 60
        self.dispatch_table[Opcode.BEQ] = 60
        self.horizontal_rom[60] = HorizontalMicrocode(
            pc_write=True, pc_src=1, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=1, alu_srcB=1, alu_op=Opcode.ADD, seq_op=MicroSeqOp.BRANCH_COND,
            next_uaddr=0, name="BEQ_EVAL"
        )
        self.vertical_rom[60] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=1, dst_sel=0, mem_ctrl=0,
            reg_write=False, seq_ctrl=MicroSeqOp.BRANCH_COND, next_uaddr=0, name="BEQ_EVAL"
        )

        # B: uPC 64
        self.dispatch_table[Opcode.B] = 64
        self.horizontal_rom[64] = HorizontalMicrocode(
            pc_write=True, pc_src=1, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=1, alu_srcB=1, alu_op=Opcode.ADD, seq_op=MicroSeqOp.FETCH,
            next_uaddr=0, name="B_JUMP"
        )
        self.vertical_rom[64] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=1, dst_sel=0, mem_ctrl=0,
            reg_write=False, seq_ctrl=MicroSeqOp.FETCH, next_uaddr=0, name="B_JUMP"
        )

        # CALL: uPC 68, 69
        self.dispatch_table[Opcode.CALL] = 68
        self.horizontal_rom[68] = HorizontalMicrocode(
            pc_write=False, pc_src=0, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=True,
            alu_srcA=1, alu_srcB=2, alu_op=Opcode.ADD, seq_op=MicroSeqOp.NEXT,
            next_uaddr=69, name="CALL_SAVE_RA"
        )
        self.vertical_rom[68] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=1, dst_sel=0, mem_ctrl=0,
            reg_write=True, seq_ctrl=MicroSeqOp.NEXT, next_uaddr=69, name="CALL_SAVE_RA"
        )
        self.horizontal_rom[69] = HorizontalMicrocode(
            pc_write=True, pc_src=1, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=1, alu_srcB=1, alu_op=Opcode.ADD, seq_op=MicroSeqOp.FETCH,
            next_uaddr=0, name="CALL_TARGET"
        )
        self.vertical_rom[69] = VerticalMicrocode(
            alu_func=Opcode.ADD, src_sel=1, dst_sel=0, mem_ctrl=0,
            reg_write=False, seq_ctrl=MicroSeqOp.FETCH, next_uaddr=0, name="CALL_TARGET"
        )

        # RET: uPC 72
        self.dispatch_table[Opcode.RET] = 72
        self.horizontal_rom[72] = HorizontalMicrocode(
            pc_write=True, pc_src=2, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=0, alu_srcB=0, alu_op=Opcode.NOP, seq_op=MicroSeqOp.FETCH,
            next_uaddr=0, name="RET_RESTORE"
        )
        self.vertical_rom[72] = VerticalMicrocode(
            alu_func=Opcode.NOP, src_sel=2, dst_sel=0, mem_ctrl=0,
            reg_write=False, seq_ctrl=MicroSeqOp.FETCH, next_uaddr=0, name="RET_RESTORE"
        )

        # NOP / BNE / BGT / BLT / TRAP: single-step micro-routines
        for _op, _uaddr, _name, _seq in (
            (Opcode.NOP, 84, "NOP_IDLE", MicroSeqOp.FETCH),
            (Opcode.BNE, 88, "BNE_EVAL", MicroSeqOp.BRANCH_COND),
            (Opcode.BGT, 92, "BGT_EVAL", MicroSeqOp.BRANCH_COND),
            (Opcode.BLT, 96, "BLT_EVAL", MicroSeqOp.BRANCH_COND),
            (Opcode.TRAP, 100, "TRAP_RAISE", MicroSeqOp.FETCH),
        ):
            _is_br = _seq == MicroSeqOp.BRANCH_COND
            self.dispatch_table[_op] = _uaddr
            self.horizontal_rom[_uaddr] = HorizontalMicrocode(
                pc_write=_is_br, pc_src=1 if _is_br else 0, mem_read=False, mem_write=False,
                mem_to_reg=False, ir_write=False, reg_write=False,
                alu_srcA=1 if _is_br else 0, alu_srcB=1 if _is_br else 0,
                alu_op=Opcode.ADD if _is_br else Opcode.NOP, seq_op=_seq,
                next_uaddr=0, name=_name
            )
            self.vertical_rom[_uaddr] = VerticalMicrocode(
                alu_func=Opcode.ADD if _is_br else Opcode.NOP, src_sel=1 if _is_br else 0,
                dst_sel=0, mem_ctrl=0, reg_write=False, seq_ctrl=_seq,
                next_uaddr=0, name=_name
            )

        # HLT: uPC 80
        self.dispatch_table[Opcode.HLT] = 80
        self.horizontal_rom[80] = HorizontalMicrocode(
            pc_write=False, pc_src=0, mem_read=False, mem_write=False,
            mem_to_reg=False, ir_write=False, reg_write=False,
            alu_srcA=0, alu_srcB=0, alu_op=Opcode.NOP, seq_op=MicroSeqOp.JUMP,
            next_uaddr=80, name="HLT_HALT"
        )
        self.vertical_rom[80] = VerticalMicrocode(
            alu_func=Opcode.NOP, src_sel=0, dst_sel=0, mem_ctrl=0,
            reg_write=False, seq_ctrl=MicroSeqOp.JUMP, next_uaddr=80, name="HLT_HALT"
        )


class MicroprogrammedCPU:
    """
    Microprogrammed RISC201 CPU Simulator.
    Executes instructions via Control Memory microcode with selectable
    Horizontal or Vertical microprogrammed control models.
    """
    def __init__(
        self,
        memory: Optional[Memory] = None,
        use_vertical: bool = False
    ):
        self.memory = memory if memory is not None else Memory()
        self.rf = RegisterFile()
        self.csr = CSRFile()
        self.alu = ALU()
        self.pmc = PMC()
        self.store = ControlStore()
        self.use_vertical = use_vertical

        # Architectural Registers
        self.pc: int = 0
        self.ir: int = 0
        self.mar: int = 0
        self.mdr: int = 0
        self.current_inst: Optional[DecodedInstruction] = None

        # Microprogrammed Control Registers
        self.upc: int = 0
        self.halted: bool = False
        self.exception_raised: bool = False
        self.last_exception: Optional[CPUException] = None
        self.total_micro_cycles: int = 0

        self.rf.reset(initial_sp=self.memory.stack_base)

    def reset(self, initial_pc: int = 0):
        self.pc = initial_pc
        self.ir = 0
        self.mar = 0
        self.mdr = 0
        self.upc = 0
        self.halted = False
        self.exception_raised = False
        self.last_exception = None
        self.total_micro_cycles = 0
        self.current_inst = None
        self.rf.reset(initial_sp=self.memory.stack_base)
        self.csr.clear_exception()
        self.pmc.reset()

    def step_micro(self) -> bool:
        """Executes one microinstruction; CPU exceptions are trapped into the CSRs
        (same behaviour as the pipelined models) instead of escaping as a Python error."""
        try:
            return self._step_micro_inner()
        except CPUException as e:
            self.exception_raised = True
            self.last_exception = e
            self.halted = True
            self.csr.trigger_exception(e.cause, e.pc, e.badvaddr)
            return False

    def _step_micro_inner(self) -> bool:
        """
        Executes a single microinstruction cycle from Control Store.
        Returns False when halted or faulted.
        """
        if self.halted:
            return False

        self.total_micro_cycles += 1
        self.pmc.tick_cycle()

        # Fetch microinstruction from Control Memory
        if self.use_vertical:
            u_inst = self.store.vertical_rom.get(self.upc)
            if not u_inst:
                raise CPUException(CSRCause.ILLEGAL_INSTRUCTION, self.pc, f"Invalid microPC: {self.upc}")
            op_name = u_inst.name
            seq_op = u_inst.seq_ctrl
            next_addr = u_inst.next_uaddr
            reg_write = u_inst.reg_write
            alu_func = u_inst.alu_func
        else:
            h_inst = self.store.horizontal_rom.get(self.upc)
            if not h_inst:
                raise CPUException(CSRCause.ILLEGAL_INSTRUCTION, self.pc, f"Invalid microPC: {self.upc}")
            op_name = h_inst.name
            seq_op = h_inst.seq_op
            next_addr = h_inst.next_uaddr
            reg_write = h_inst.reg_write
            alu_func = h_inst.alu_op

        # Execute micro-operation based on current uPC
        if self.upc == 0:  # FETCH_READ
            self.ir = self.memory.read_word(self.pc, self.pc)
            self.current_inst = decode_instruction(self.ir)
            self.pc += 4

        elif self.upc == 1:  # DISPATCH
            pass  # Opcode dispatch handled in sequencer below

        else:
            # Opcode micro-sequence execution
            inst = self.current_inst
            if inst:
                if inst.opcode == Opcode.HLT:
                    self.halted = True
                    self.pmc.commit_instruction()
                    return False

                # Multi-step routines (CALL, LD) must apply their architectural effect
                # exactly once: on the last micro-step of the sequence.
                is_final_step = seq_op in (MicroSeqOp.FETCH, MicroSeqOp.BRANCH_COND)
                if is_final_step:
                    inst_pc = self.pc - 4  # address of the current instruction

                    if inst.opcode == Opcode.TRAP:
                        cause = (CSRCause(inst.trap_id)
                                 if inst.trap_id in CSRCause._value2member_map_
                                 else CSRCause.TRAP_CALL)
                        raise CPUException(cause, inst_pc, f"TRAP triggered with code {inst.trap_id}")

                    valA = self.rf.read(inst.rs1)
                    res = 0
                    # Only true ALU instructions touch the ALU (keeps CMP flags intact)
                    if (inst.opcode != Opcode.NOP and not is_branch_op(inst.opcode)
                            and not is_memory_op(inst)):
                        if inst.is_imm:
                            valB = inst.imm
                        elif inst.opcode == Opcode.MOV:
                            valB = self.rf.read(inst.rs1)
                        else:
                            valB = self.rf.read(inst.rs2)
                        try:
                            res = self.alu.execute(inst.opcode, valA, valB, update_flags=True)
                        except DivisionByZeroException:
                            raise CPUException(CSRCause.DIVISION_BY_ZERO, inst_pc, "ALU Division by zero")

                    flags = self.alu.flags
                    target = inst_pc + (inst.offset * 4)

                    if inst.opcode == Opcode.LD:
                        addr = to_signed32(valA + inst.imm)
                        self.rf.write(inst.dest_reg, self.memory.read_word(addr, inst_pc))
                    elif inst.opcode == Opcode.ST:
                        addr = to_signed32(valA + inst.imm)
                        self.memory.write_word(addr, self.rf.read(inst.rd), inst_pc)
                    elif inst.opcode == Opcode.CALL:
                        self.rf.write(15, self.pc)  # return address = next instruction
                        self.pc = target
                    elif inst.opcode == Opcode.RET:
                        self.pc = self.rf.ra
                    elif inst.opcode == Opcode.B:
                        self.pc = target
                    elif inst.opcode == Opcode.BEQ and flags.Z:
                        self.pc = target
                    elif inst.opcode == Opcode.BNE and not flags.Z:
                        self.pc = target
                    elif inst.opcode == Opcode.BGT and (not flags.Z and flags.N == flags.V):
                        self.pc = target
                    elif inst.opcode == Opcode.BLT and (flags.N != flags.V):
                        self.pc = target
                    elif reg_write and inst.writes_rf:
                        self.rf.write(inst.dest_reg, res)

        # Micro-sequencing logic
        if seq_op == MicroSeqOp.NEXT:
            self.upc = self.upc + 1
        elif seq_op == MicroSeqOp.DISPATCH:
            if self.current_inst:
                target_uaddr = self.store.dispatch_table.get(self.current_inst.opcode, 0)
                self.upc = target_uaddr
            else:
                self.upc = 0
        elif seq_op == MicroSeqOp.FETCH:
            self.upc = 0
            self.pmc.commit_instruction()
        elif seq_op == MicroSeqOp.JUMP:
            self.upc = next_addr
        elif seq_op == MicroSeqOp.BRANCH_COND:
            self.upc = 0
            self.pmc.commit_instruction()

        return True

    def step_macro(self) -> bool:
        """Executes until one full RISC201 macro-instruction finishes (uPC returns to 0)."""
        if self.halted:
            return False
        # Run at least 1 micro step
        cont = self.step_micro()
        while cont and self.upc != 0 and not self.halted:
            cont = self.step_micro()
        return cont

    def run(self, max_micro_cycles: int = 500000) -> bool:
        cycles = 0
        while not self.halted and cycles < max_micro_cycles:
            cycles += 1
            if not self.step_micro():
                break
        return self.halted
