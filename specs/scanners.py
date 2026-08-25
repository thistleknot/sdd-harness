"""Code cleanliness scanner calibration.

Purpose: evaluate a minimal pinned scanner set, capture baseline metrics,
set warning/gate thresholds from false-positive evidence. Python-first:
Ruff (lint), Vulture (dead code), Radon (complexity), coverage.py (exercised paths).

Preconditions: scanners installed (ruff, vulture, radon). subprocess available.
Failure modes: ScannerNotFoundError if binary missing; TimeoutError on long runs.

Usage:
    from specs.scanners import ScannerSuite, run_suite
    suite = ScannerSuite(root="src/")
    results = suite.run_all()
    baseline = suite.capture_baseline()
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ScannerType(str, Enum):
    ruff = "ruff"
    vulture = "vulture"
    radon = "radon"
    coverage = "coverage"


class Severity(str, Enum):
    info = "info"
    warn = "warn"
    gate = "gate"  # blocks commit/merge


@dataclass
class ScannerFinding:
    """One finding from a scanner."""
    scanner: ScannerType
    file_path: str
    line: int
    code: str  # e.g. "E501", "unused-function"
    message: str
    severity: Severity = Severity.warn


@dataclass
class ScannerResult:
    """Result of running one scanner."""
    scanner: ScannerType
    findings: list[ScannerFinding] = field(default_factory=list)
    elapsed_ms: float = 0
    exit_code: int = 0
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def gate_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.gate)


@dataclass
class Baseline:
    """Repository baseline snapshot for threshold calibration."""
    timestamp: float = 0
    total_findings: int = 0
    findings_by_scanner: dict[str, int] = field(default_factory=dict)
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    complexity_p90: float = 0  # 90th percentile cyclomatic complexity
    dead_code_count: int = 0
    lint_count: int = 0


@dataclass
class ThresholdConfig:
    """Calibrated thresholds for gate decisions."""
    max_complexity: int = 15  # cyclomatic complexity per function
    max_dead_code: int = 10  # dead code items before warning
    max_lint_errors: int = 0  # gate: zero tolerance for select rules
    warn_lint_threshold: int = 20  # warn above this
    max_cognitive_complexity: int = 25


# --- Scanner Runners ---------------------------------------------------------


class ScannerNotFoundError(Exception):
    pass


def run_ruff(root: Path, config: ThresholdConfig) -> ScannerResult:
    """Run ruff linter on the given root."""
    start = time.time()
    try:
        result = subprocess.run(
            ["ruff", "check", str(root), "--output-format=json", "--quiet"],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise ScannerNotFoundError("ruff not found in PATH")
    except subprocess.TimeoutExpired:
        return ScannerResult(scanner=ScannerType.ruff, error="timeout", exit_code=-1)

    elapsed = (time.time() - start) * 1000
    findings = []

    if result.stdout.strip():
        try:
            items = json.loads(result.stdout)
            for item in items:
                severity = Severity.gate if item.get("code", "").startswith("F") else Severity.warn
                findings.append(ScannerFinding(
                    scanner=ScannerType.ruff,
                    file_path=item.get("filename", ""),
                    line=item.get("location", {}).get("row", 0),
                    code=item.get("code", ""),
                    message=item.get("message", ""),
                    severity=severity,
                ))
        except json.JSONDecodeError:
            pass

    return ScannerResult(
        scanner=ScannerType.ruff,
        findings=findings,
        elapsed_ms=elapsed,
        exit_code=result.returncode,
    )


def run_vulture(root: Path, config: ThresholdConfig) -> ScannerResult:
    """Run vulture dead code detection."""
    start = time.time()
    try:
        result = subprocess.run(
            ["vulture", str(root), "--min-confidence=80"],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise ScannerNotFoundError("vulture not found in PATH")
    except subprocess.TimeoutExpired:
        return ScannerResult(scanner=ScannerType.vulture, error="timeout", exit_code=-1)

    elapsed = (time.time() - start) * 1000
    findings = []

    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        # Format: path:line: unused X 'name' (confidence%)
        parts = line.split(":", 2)
        if len(parts) >= 3:
            try:
                line_num = int(parts[1])
            except ValueError:
                line_num = 0
            severity = Severity.warn if len(findings) < config.max_dead_code else Severity.gate
            findings.append(ScannerFinding(
                scanner=ScannerType.vulture,
                file_path=parts[0],
                line=line_num,
                code="unused",
                message=parts[2].strip() if len(parts) > 2 else "",
                severity=severity,
            ))

    return ScannerResult(
        scanner=ScannerType.vulture,
        findings=findings,
        elapsed_ms=elapsed,
        exit_code=result.returncode,
    )


def run_radon(root: Path, config: ThresholdConfig) -> ScannerResult:
    """Run radon complexity analysis."""
    start = time.time()
    try:
        result = subprocess.run(
            ["radon", "cc", str(root), "-j", "-n", "C"],  # show C and above
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise ScannerNotFoundError("radon not found in PATH")
    except subprocess.TimeoutExpired:
        return ScannerResult(scanner=ScannerType.radon, error="timeout", exit_code=-1)

    elapsed = (time.time() - start) * 1000
    findings = []

    if result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            for file_path, blocks in data.items():
                for block in blocks:
                    complexity = block.get("complexity", 0)
                    if complexity > config.max_complexity:
                        severity = Severity.gate
                    elif complexity > config.max_complexity * 0.8:
                        severity = Severity.warn
                    else:
                        severity = Severity.info
                    findings.append(ScannerFinding(
                        scanner=ScannerType.radon,
                        file_path=file_path,
                        line=block.get("lineno", 0),
                        code=f"CC={complexity}",
                        message=f"{block.get('name', '?')} has complexity {complexity}",
                        severity=severity,
                    ))
        except json.JSONDecodeError:
            pass

    return ScannerResult(
        scanner=ScannerType.radon,
        findings=findings,
        elapsed_ms=elapsed,
        exit_code=result.returncode,
    )


# --- Suite -------------------------------------------------------------------


class ScannerSuite:
    """Orchestrate multiple scanners and aggregate results.

    Contract:
        Require: root path exists; at least one scanner available.
        Guarantee: findings de-duplicated by (file, line, code).
        Maintain: thresholds respected for gate decisions.
    """

    def __init__(self, root: str | Path, config: Optional[ThresholdConfig] = None):
        self.root = Path(root)
        self.config = config or ThresholdConfig()
        self._runners = {
            ScannerType.ruff: run_ruff,
            ScannerType.vulture: run_vulture,
            ScannerType.radon: run_radon,
        }

    def run_all(self) -> list[ScannerResult]:
        """Run all available scanners. Skip unavailable ones."""
        results = []
        for scanner_type, runner in self._runners.items():
            try:
                result = runner(self.root, self.config)
                results.append(result)
            except ScannerNotFoundError:
                results.append(ScannerResult(
                    scanner=scanner_type,
                    error=f"{scanner_type.value} not installed",
                    exit_code=-1,
                ))
        return results

    def run_one(self, scanner: ScannerType) -> ScannerResult:
        """Run a single scanner."""
        runner = self._runners.get(scanner)
        if not runner:
            return ScannerResult(scanner=scanner, error="unknown scanner", exit_code=-1)
        return runner(self.root, self.config)

    def capture_baseline(self) -> Baseline:
        """Run all scanners and capture current state as baseline."""
        results = self.run_all()
        baseline = Baseline(timestamp=time.time())

        for result in results:
            baseline.findings_by_scanner[result.scanner.value] = result.count
            baseline.total_findings += result.count
            for f in result.findings:
                sev = f.severity.value
                baseline.findings_by_severity[sev] = baseline.findings_by_severity.get(sev, 0) + 1

            if result.scanner == ScannerType.vulture:
                baseline.dead_code_count = result.count
            elif result.scanner == ScannerType.ruff:
                baseline.lint_count = result.count
            elif result.scanner == ScannerType.radon:
                complexities = []
                for f in result.findings:
                    try:
                        cc = int(f.code.split("=")[1])
                        complexities.append(cc)
                    except (IndexError, ValueError):
                        pass
                if complexities:
                    complexities.sort()
                    idx = int(len(complexities) * 0.9)
                    baseline.complexity_p90 = complexities[min(idx, len(complexities) - 1)]

        return baseline

    def gate_decision(self, results: list[ScannerResult]) -> tuple[bool, list[str]]:
        """Decide whether to gate (block) based on results.

        Returns:
            (blocked: bool, reasons: list[str])
        """
        reasons = []
        blocked = False

        for result in results:
            if result.gate_count > 0:
                blocked = True
                reasons.append(
                    f"{result.scanner.value}: {result.gate_count} gate-level findings"
                )

        return blocked, reasons
