from __future__ import annotations

import asyncio
import logging
import time

from db.database import get_db_session
from program_generator_v5.layer4_program_builder import build_program as build_legacy_program

from .assembler import assemble_program, trace_from_program
from .block_planner import build_block_plan
from .critic import run_structured_critic, should_run_critic
from .directive_compiler import compile_program_directive
from .kg_loader import build_fallback_snapshot, ensure_active_kg_snapshot
from .repair import repair_program
from .scoring import build_validation_score, compute_quality_metrics
from .schemas import BlockPlanV7, ProgramArtifactV7
from .serializer import serialize_v7_program
from .validators import summarize_validation_issues, validate_program_artifact


logger = logging.getLogger(__name__)


async def generate_program_v7(
    input_data: dict,
    openai_client=None,
    use_llm: bool = True,
) -> dict:
    start_time = time.time()
    timings: dict[str, float] = {}

    layer_start = time.time()
    directive = compile_program_directive(input_data)
    timings["directive"] = time.time() - layer_start
    logger.info("[V7] Compiled directive")

    layer_start = time.time()
    try:
        with get_db_session() as db:
            snapshot = ensure_active_kg_snapshot(db)
    except Exception as exc:
        logger.warning("[V7] Falling back to in-memory KG snapshot: %s", exc)
        snapshot = build_fallback_snapshot()
    timings["kg_load"] = time.time() - layer_start
    logger.info("[V7] Loaded KG snapshot %s", snapshot.version_label)

    layer_start = time.time()
    block_plan = await build_block_plan(
        directive=directive,
        snapshot=snapshot,
        openai_client=openai_client,
        use_llm=use_llm,
    )
    timings["block_plan"] = time.time() - layer_start
    logger.info("[V7] Built block plan")

    layer_start = time.time()
    program, assembly_trace = assemble_program(block_plan=block_plan, snapshot=snapshot)
    timings["assembly"] = time.time() - layer_start
    logger.info("[V7] Assembled deterministic program")

    layer_start = time.time()
    program, assembly_trace, validation_issues, repair_log, metrics = _select_best_program_candidate(
        block_plan=block_plan,
        initial_program=program,
        initial_trace=assembly_trace,
    )
    timings["validate_repair"] = time.time() - layer_start
    logger.info("[V7] Validation summary: %s", summarize_validation_issues(validation_issues))
    timings["metrics"] = 0.0

    artifact = ProgramArtifactV7(
        directive=directive,
        kg_version=snapshot.version_label,
        profile=block_plan.profile,
        strategy=block_plan.strategy,
        volume_allocation=block_plan.volume_allocation,
        block_plan=block_plan,
        program=program,
        assembly_trace=assembly_trace,
        validation_issues=validation_issues,
        repair_log=repair_log,
        critic=None,
        metrics=metrics,
        prompt_version="v7_prompt_1",
    )

    if use_llm and openai_client and should_run_critic(artifact):
        layer_start = time.time()
        artifact.critic = await run_structured_critic(artifact, openai_client)
        timings["critic"] = time.time() - layer_start
    else:
        timings["critic"] = 0.0

    total_time = time.time() - start_time
    artifact.program.generation_time_seconds = total_time
    output = serialize_v7_program(artifact)
    output["timings"] = timings
    output["timings"]["total"] = total_time
    output["stats"]["generation_time_seconds"] = total_time
    return output


def generate_program_v7_sync(input_data: dict, use_llm: bool = False) -> dict:
    return asyncio.run(generate_program_v7(
        input_data=input_data,
        openai_client=None,
        use_llm=use_llm,
    ))


def _select_best_program_candidate(
    *,
    block_plan: BlockPlanV7,
    initial_program,
    initial_trace,
):
    slot_program, slot_trace, slot_issues, slot_repairs, slot_metrics = _finalize_candidate(
        program=initial_program,
        assembly_trace=initial_trace,
        block_plan=block_plan,
        assembler_name="slot_v7",
    )

    legacy_program = build_legacy_program(
        profile=block_plan.profile,
        strategy=block_plan.strategy,
        volume_allocation=block_plan.volume_allocation,
    )
    legacy_trace = trace_from_program(legacy_program)
    legacy_program, legacy_trace, legacy_issues, legacy_repairs, legacy_metrics = _finalize_candidate(
        program=legacy_program,
        assembly_trace=legacy_trace,
        block_plan=block_plan,
        assembler_name="legacy_builder_fallback",
    )

    if _candidate_score(legacy_issues, legacy_metrics) > _candidate_score(slot_issues, slot_metrics):
        return legacy_program, legacy_trace, legacy_issues, legacy_repairs, legacy_metrics
    return slot_program, slot_trace, slot_issues, slot_repairs, slot_metrics


def _finalize_candidate(
    *,
    program,
    assembly_trace,
    block_plan: BlockPlanV7,
    assembler_name: str,
):
    validation_issues = validate_program_artifact(
        program=program,
        block_plan=block_plan,
        assembly_trace=assembly_trace,
    )
    program, repair_log = repair_program(
        program=program,
        block_plan=block_plan,
        issues=validation_issues,
        assembly_trace=assembly_trace,
    )
    validation_issues = validate_program_artifact(
        program=program,
        block_plan=block_plan,
        assembly_trace=assembly_trace,
    )
    metrics = compute_quality_metrics(
        program=program,
        block_plan=block_plan,
        assembly_trace=assembly_trace,
    )
    metrics["selected_assembler"] = assembler_name
    metrics["validation_score"] = build_validation_score(metrics, len(validation_issues))
    return program, assembly_trace, validation_issues, repair_log, metrics


def _candidate_score(issues, metrics) -> float:
    summary = summarize_validation_issues(issues)
    penalty = (summary["critical_count"] * 100.0) + (summary["major_count"] * 10.0) + summary["warning_count"]
    return metrics.get("validation_score", 0.0) - penalty
