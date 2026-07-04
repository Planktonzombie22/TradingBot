from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class DeploymentProfile:
    name: str
    command: str
    environment: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def local_windows_task_profile() -> DeploymentProfile:
    return DeploymentProfile(
        name="windows-task",
        command=r"trading_env\Scripts\python.exe main.py paper --provider alpaca --execution-mode paper",
        environment={"PAPER_TRADING": "true", "EXECUTION_MODE": "paper"},
        notes=["Run only after the paper soak checklist passes.", "Use Task Scheduler with restart-on-failure disabled until soak is clean."],
    )


def docker_profile() -> DeploymentProfile:
    return DeploymentProfile(
        name="docker",
        command="python main.py paper --provider alpaca --execution-mode paper",
        environment={"PAPER_TRADING": "true", "EXECUTION_MODE": "paper"},
        notes=["Mount .env as a secret or env file.", "Persist runs/ as a volume."],
    )


def small_server_profile() -> DeploymentProfile:
    return DeploymentProfile(
        name="small-server",
        command="python main.py paper --provider alpaca --execution-mode paper",
        environment={"PAPER_TRADING": "true", "EXECUTION_MODE": "paper"},
        notes=["Use a process supervisor only after manual paper sessions are stable.", "Forward logs and alerts before unattended runs."],
    )
