from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

VALIDATED_MODE = "validated"
EXPLORATORY_MODE = "exploratory"
SUPPORTED_EXECUTION_MODES = {VALIDATED_MODE, EXPLORATORY_MODE}


@dataclass(frozen=True)
class ExecutionPolicy:
    """Resolved policy controlling reproducibility and runtime LLM use."""

    mode: str
    allow_runtime_llm: bool
    runtime_llm_requested: bool
    runtime_llm_effective: bool
    deterministic_build: bool
    final_claim_eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload


def _llm2_requested(context: Mapping[str, Any]) -> bool:
    llm = context.get("llm", {}) or {}
    llm2 = llm.get("llm2", {}) or {}
    return bool(llm2.get("enabled", False))


def resolve_execution_policy(context: Mapping[str, Any]) -> ExecutionPolicy:
    """Resolve deterministic validated mode or provisional exploratory mode.

    Validated mode is the default. It forbids runtime LLM calls so that the
    registered contract, model, catalog, and inventory completely determine
    the planner inputs. LLMs may be used before registration to author or
    propose contract content.
    """

    raw = context.get("execution_policy", {}) or {}
    mode = str(raw.get("mode", VALIDATED_MODE) or VALIDATED_MODE).strip().lower()
    allow_runtime_llm = bool(raw.get("allow_runtime_llm", False))
    requested = _llm2_requested(context)
    errors: list[str] = []
    warnings: list[str] = []

    if mode not in SUPPORTED_EXECUTION_MODES:
        errors.append(
            f"Unsupported execution_policy.mode {mode!r}; expected validated or exploratory."
        )

    if mode == VALIDATED_MODE:
        if allow_runtime_llm:
            errors.append(
                "Validated mode cannot set execution_policy.allow_runtime_llm=true."
            )
        if requested:
            errors.append(
                "Validated mode cannot enable llm.llm2 at runtime. Run LLM-assisted "
                "classification during contract authoring, save the reviewed decisions "
                "in the contract, and set llm.llm2.enabled=false."
            )
    elif mode == EXPLORATORY_MODE:
        warnings.append(
            "Exploratory mode is provisional and cannot produce a validated final claim."
        )
        if requested and not allow_runtime_llm:
            errors.append(
                "Exploratory runtime LLM use requires "
                "execution_policy.allow_runtime_llm=true."
            )

    effective = bool(
        mode == EXPLORATORY_MODE
        and allow_runtime_llm
        and requested
        and not errors
    )
    deterministic = not effective
    final_claim_eligible = bool(mode == VALIDATED_MODE and deterministic and not errors)

    return ExecutionPolicy(
        mode=mode,
        allow_runtime_llm=allow_runtime_llm,
        runtime_llm_requested=requested,
        runtime_llm_effective=effective,
        deterministic_build=deterministic,
        final_claim_eligible=final_claim_eligible,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
