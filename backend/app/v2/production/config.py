"""FASE 10 — Production configuration.

Centralizes operational settings: timeouts, batch size, workers,
memory limits and feature flags. No hardcoded values scattered
across the production modules.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


@dataclass
class ProductionConfig:
    timeouts: dict = field(default_factory=lambda: {
        "ocr": 60.0,
        "assembly": 30.0,
        "segmentation": 20.0,
        "parser": 10.0,
        "knowledge": 10.0,
        "validator": 10.0,
        "certification": 10.0,
        "total": 300.0,
    })
    batch_size: int = 10
    workers: int = 4
    memory_limits: dict = field(default_factory=lambda: {
        "max_mb": 512.0,
        "ocr_mb": 128.0,
        "batch_mb": 256.0,
    })
    feature_flags: dict = field(default_factory=lambda: {
        "ocr_enabled": True,
        "knowledge_enabled": True,
        "certification_enabled": True,
        "structured_logs": True,
        "memory_tracking": True,
    })
    output_dir: str = "output"
    log_dir: str = "logs"
    log_file: str = "pipeline.log"

    def output_path(self) -> Path:
        return _package_dir() / self.output_dir

    def log_path(self) -> Path:
        return _package_dir() / self.log_dir

    def log_file_path(self) -> Path:
        return self.log_path() / self.log_file

    def validate(self) -> list[str]:
        errors = []
        if self.batch_size < 1:
            errors.append("batch_size must be >= 1")
        if self.workers < 1:
            errors.append("workers must be >= 1")
        for name, value in self.timeouts.items():
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"timeout '{name}' must be a positive number")
        for name, value in self.memory_limits.items():
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"memory_limit '{name}' must be a positive number")
        if not isinstance(self.feature_flags, dict) or not self.feature_flags:
            errors.append("feature_flags must be a non-empty dict")
        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    def to_dict(self) -> dict:
        return {
            "timeouts": dict(self.timeouts),
            "batch_size": self.batch_size,
            "workers": self.workers,
            "memory_limits": dict(self.memory_limits),
            "feature_flags": dict(self.feature_flags),
            "output_dir": self.output_dir,
            "log_dir": self.log_dir,
            "log_file": self.log_file,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProductionConfig":
        return cls(
            timeouts=dict(data.get("timeouts", {})),
            batch_size=int(data.get("batch_size", 10)),
            workers=int(data.get("workers", 4)),
            memory_limits=dict(data.get("memory_limits", {})),
            feature_flags=dict(data.get("feature_flags", {})),
            output_dir=str(data.get("output_dir", "output")),
            log_dir=str(data.get("log_dir", "logs")),
            log_file=str(data.get("log_file", "pipeline.log")),
        )

    def to_env_dict(self) -> dict:
        return {
            "REMATEUP_BATCH_SIZE": str(self.batch_size),
            "REMATEUP_WORKERS": str(self.workers),
            "REMATEUP_TOTAL_TIMEOUT_S": str(self.timeouts.get("total", 300.0)),
            "REMATEUP_MAX_MEMORY_MB": str(self.memory_limits.get("max_mb", 512.0)),
        }

    @classmethod
    def from_env(cls) -> "ProductionConfig":
        cfg = cls()
        if os.getenv("REMATEUP_BATCH_SIZE"):
            cfg.batch_size = int(os.getenv("REMATEUP_BATCH_SIZE"))
        if os.getenv("REMATEUP_WORKERS"):
            cfg.workers = int(os.getenv("REMATEUP_WORKERS"))
        return cfg


DEFAULT_CONFIG = ProductionConfig()


def get_default() -> ProductionConfig:
    return ProductionConfig()


def load_config(data: dict | None = None) -> ProductionConfig:
    if data is None:
        return get_default()
    return ProductionConfig.from_dict(data)
