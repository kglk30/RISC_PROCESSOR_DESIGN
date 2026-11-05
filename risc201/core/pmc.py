"""
Hardware Performance Monitoring Counters (PMCs)
Tracks hardware runtime execution metrics:
- Cycle count
- Instruction retired count
- Stall cycles (Data hazard stalls, load-use stalls, structural stalls)
- Branch evaluation and misprediction counts
- Calculates CPI (Cycles Per Instruction) and IPC (Instructions Per Cycle)
"""

from typing import Dict, Any

class PMC:
    """
    Hardware Performance Monitoring Unit.
    """
    def __init__(self):
        self.cycle_count: int = 0
        self.instruction_count: int = 0
        self.stall_count: int = 0
        self.data_hazard_stalls: int = 0
        self.load_use_stalls: int = 0
        self.structural_stalls: int = 0
        self.branch_count: int = 0
        self.branch_mispredict_count: int = 0
        self.forwarding_events: int = 0

    def reset(self):
        self.cycle_count = 0
        self.instruction_count = 0
        self.stall_count = 0
        self.data_hazard_stalls = 0
        self.load_use_stalls = 0
        self.structural_stalls = 0
        self.branch_count = 0
        self.branch_mispredict_count = 0
        self.forwarding_events = 0

    def tick_cycle(self):
        self.cycle_count += 1

    def commit_instruction(self):
        self.instruction_count += 1

    def record_stall(self, is_load_use: bool = False, is_structural: bool = False):
        self.stall_count += 1
        if is_load_use:
            self.load_use_stalls += 1
            self.data_hazard_stalls += 1
        elif is_structural:
            self.structural_stalls += 1
        else:
            self.data_hazard_stalls += 1

    def record_branch(self, mispredicted: bool):
        self.branch_count += 1
        if mispredicted:
            self.branch_mispredict_count += 1

    def record_forwarding(self):
        self.forwarding_events += 1

    @property
    def cpi(self) -> float:
        """Cycles Per Instruction."""
        if self.instruction_count == 0:
            return 0.0
        return self.cycle_count / self.instruction_count

    @property
    def ipc(self) -> float:
        """Instructions Per Cycle."""
        if self.cycle_count == 0:
            return 0.0
        return self.instruction_count / self.cycle_count

    @property
    def branch_mispredict_rate(self) -> float:
        """Branch misprediction percentage."""
        if self.branch_count == 0:
            return 0.0
        return (self.branch_mispredict_count / self.branch_count) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Cycles": self.cycle_count,
            "Instructions Committed": self.instruction_count,
            "Total Stalls": self.stall_count,
            "Data Hazard Stalls": self.data_hazard_stalls,
            "Load-Use Stalls": self.load_use_stalls,
            "Structural Stalls": self.structural_stalls,
            "Branches Evaluated": self.branch_count,
            "Branch Mispredicts": self.branch_mispredict_count,
            "Mispredict Rate (%)": f"{self.branch_mispredict_rate:.2f}%",
            "Forwarding Events": self.forwarding_events,
            "CPI": f"{self.cpi:.3f}",
            "IPC": f"{self.ipc:.3f}",
        }

    def format_summary(self) -> str:
        d = self.to_dict()
        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║        HARDWARE PERFORMANCE MONITORING COUNTERS (PMC)        ║",
            "╠══════════════════════════════════════════════════════════════╣",
        ]
        for k, v in d.items():
            lines.append(f"║  {k:<28}: {str(v):>26}  ║")
        lines.append("╚══════════════════════════════════════════════════════════════╝")
        return "\n".join(lines)
