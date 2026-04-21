"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# OpenAI — supports both the standard name and the common typo variant
OPENAI_API_KEY: str = (
    os.getenv("OPENAI_API_KEY")
    or os.getenv("OPAI_API_KEY")
    or ""
)
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# Pipeline behaviour
MAX_REPAIR_ATTEMPTS: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "3"))
MAX_RTR_FDR_CYCLES: int = int(os.getenv("MAX_RTR_FDR_CYCLES", "3"))

# Paths
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_INPUT_DIR: Path = PROJECT_ROOT / "data" / "input"
DATA_OUTPUT_DIR: Path = PROJECT_ROOT / "data" / "output"
LOG_DIR: Path = PROJECT_ROOT / "logs"
PIPELINE_DIR: Path = PROJECT_ROOT / "pipeline"

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
