"""
Branch Predictor and Branch Target Buffer (BTB)
Implements:
1. Static Predictors (Always Not-Taken, Always Taken)
2. Dynamic 2-bit Saturating Counter Predictor:
   - 00: Strongly Not-Taken (SNT)
   - 01: Weakly Not-Taken (WNT)
   - 10: Weakly Taken (WT)
   - 11: Strongly Taken (ST)
3. Direct-mapped / Associative Branch Target Buffer (BTB)
"""

from enum import Enum
from typing import Dict, Tuple, Optional
from risc201.core.isa import is_branch_op, Opcode, to_unsigned32

class PredictorMode(str, Enum):
    STATIC_NOT_TAKEN = "static_not_taken"
    STATIC_TAKEN = "static_taken"
    DYNAMIC_2BIT = "dynamic_2bit"

class BranchPredictor:
    """
    Dynamic 2-bit Saturating Counter Branch Predictor with Branch Target Buffer (BTB).
    """
    def __init__(self, mode: PredictorMode = PredictorMode.DYNAMIC_2BIT, btb_size: int = 64):
        self.mode = mode
        self.btb_size = btb_size
        # BTB: pc -> target_pc
        self.btb: Dict[int, int] = {}
        # 2-bit counters: pc -> state (0..3)
        # Default state: 01 (Weakly Not-Taken) or 10 (Weakly Taken)
        self.counters: Dict[int, int] = {}

    def reset(self):
        self.btb.clear()
        self.counters.clear()

    def get_counter_state(self, pc: int) -> int:
        # Default to Weakly Not-Taken (1)
        return self.counters.get(pc, 1)

    def predict(self, pc: int, opcode: int, default_next_pc: int) -> Tuple[bool, int]:
        """
        Predict branch direction and target address.
        Returns: (predicted_taken, predicted_target_pc)
        """
        # Unconditional branches and calls are always taken
        if opcode in (Opcode.B, Opcode.CALL):
            target = self.btb.get(pc, default_next_pc)
            return True, target

        if opcode == Opcode.RET:
            # RET target comes from register, typically predicted via RAS (or not taken in static)
            target = self.btb.get(pc, default_next_pc)
            return True, target

        if not is_branch_op(opcode):
            return False, default_next_pc

        if self.mode == PredictorMode.STATIC_NOT_TAKEN:
            return False, default_next_pc

        elif self.mode == PredictorMode.STATIC_TAKEN:
            target = self.btb.get(pc, default_next_pc)
            return True, target

        else: # DYNAMIC_2BIT
            state = self.get_counter_state(pc)
            # Predict taken if state is 2 (Weakly Taken) or 3 (Strongly Taken)
            predict_taken = (state >= 2)
            if predict_taken and pc in self.btb:
                return True, self.btb[pc]
            return False, default_next_pc

    def update(self, pc: int, opcode: int, actual_taken: bool, actual_target: int):
        """
        Update the 2-bit counter and BTB entry based on the actual branch outcome.
        """
        if not is_branch_op(opcode):
            return

        pc = to_unsigned32(pc)
        actual_target = to_unsigned32(actual_target)

        # Update BTB if branch was taken
        if actual_taken:
            self.btb[pc] = actual_target

        if self.mode == PredictorMode.DYNAMIC_2BIT:
            current_state = self.get_counter_state(pc)
            if actual_taken:
                # Increment towards 3 (Strongly Taken)
                new_state = min(3, current_state + 1)
            else:
                # Decrement towards 0 (Strongly Not Taken)
                new_state = max(0, current_state - 1)
            self.counters[pc] = new_state
