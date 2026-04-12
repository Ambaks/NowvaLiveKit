"""
Export the active V7 knowledge graph to an Obsidian-compatible vault.

The database remains the source of truth. This exporter emits a browsable,
mostly read-only vault snapshot with markdown notes and a few canvas maps.

Usage:
    python tools/kg_sync/export_obsidian_vault.py
    python tools/kg_sync/export_obsidian_vault.py path/to/output
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db.database import get_db_session  # noqa: E402
from program_generator_v7.kg_loader import build_fallback_snapshot, ensure_active_kg_snapshot  # noqa: E402


DEFAULT_OUTPUT = ROOT / "knowledge_graph" / "obsidian_vault"


def export_obsidian_vault(output_dir: Path = DEFAULT_OUTPUT) -> Path:
    snapshot = _load_snapshot()
    output_dir.mkdir(parents=True, exist_ok=True)

    families_dir = output_dir / "families"
    exercises_dir = output_dir / "exercises"
    roles_dir = output_dir / "session_roles"
    blocks_dir = output_dir / "block_templates"
    progressions_dir = output_dir / "progression_templates"
    constraints_dir = output_dir / "constraints"
    canvases_dir = output_dir / "canvases"

    for directory in (
        families_dir,
        exercises_dir,
        roles_dir,
        blocks_dir,
        progressions_dir,
        constraints_dir,
        canvases_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    family_map = defaultdict(list)
    relations_by_src = defaultdict(list)
    for relation in snapshot.relations:
        relations_by_src[relation.src_id].append(relation)
    for exercise in snapshot.exercises.values():
        family_map[exercise.family_id].append(exercise)

    for family_id, exercises in sorted(family_map.items()):
        body = [
            f"# {family_id}",
            "",
            "## Exercises",
            *[f"- [[exercises/{exercise.canonical_id}|{exercise.name}]]" for exercise in sorted(exercises, key=lambda item: item.name)],
        ]
        _write_note(
            families_dir / f"{family_id}.md",
            {
                "type": "exercise_family",
                "source_of_truth": "db",
                "kg_version": snapshot.version_label,
                "family_id": family_id,
                "exercise_ids": [exercise.canonical_id for exercise in exercises],
                "movement_patterns": sorted({exercise.movement_pattern for exercise in exercises}),
            },
            "\n".join(body),
        )

    for exercise in sorted(snapshot.exercises.values(), key=lambda item: item.canonical_id):
        body = [
            f"# {exercise.name}",
            "",
            f"Family: [[families/{exercise.family_id}|{exercise.family_id}]]",
            "",
            "## Primary Muscles",
            *[f"- {muscle}" for muscle in exercise.stimulus.get("primary_muscles", [])],
            "",
            "## Relations",
        ]
        relations = relations_by_src.get(exercise.canonical_id, [])
        if relations:
            body.extend(
                f"- `{relation.relation_type}` -> [[exercises/{relation.dst_id}|{relation.dst_id}]]"
                for relation in relations[:20]
            )
        else:
            body.append("- None")

        body.extend([
            "",
            "## Notes",
            f"- Movement pattern: `{exercise.movement_pattern}`",
            f"- Exercise type: `{exercise.exercise_type}`",
            f"- Equipment tier: `{exercise.equipment_min}`",
            f"- VBT eligible: `{exercise.vbt_eligible}`",
        ])

        _write_note(
            exercises_dir / f"{exercise.canonical_id}.md",
            {
                "type": "exercise",
                "source_of_truth": "db",
                "kg_version": snapshot.version_label,
                "canonical_id": exercise.canonical_id,
                "name": exercise.name,
                "family_id": exercise.family_id,
                "movement_pattern": exercise.movement_pattern,
                "exercise_type": exercise.exercise_type,
                "equipment_min": exercise.equipment_min,
                "difficulty": exercise.difficulty,
                "vbt_eligible": exercise.vbt_eligible,
                "tags": exercise.tags,
                "fatigue": exercise.fatigue,
                "stimulus": exercise.stimulus,
            },
            "\n".join(body),
        )

    for role in sorted(snapshot.session_roles.values(), key=lambda item: item.role_id):
        _write_note(
            roles_dir / f"{role.role_id}.md",
            {
                "type": "session_role",
                "source_of_truth": "db",
                "kg_version": snapshot.version_label,
                "role_id": role.role_id,
                "goal": role.goal,
                "session_type": role.session_type,
                "required_patterns": role.required_patterns,
                "optional_patterns": role.optional_patterns,
                "target_muscles": role.target_muscles,
                "fatigue_budget": role.fatigue_budget,
            },
            "\n".join([
                f"# {role.label}",
                "",
                "## Required Patterns",
                *[f"- `{pattern}`" for pattern in role.required_patterns],
                "",
                "## Optional Patterns",
                *_list_or_none([f"- `{pattern}`" for pattern in role.optional_patterns]),
                "",
                "## Sequencing Hints",
                *_list_or_none([f"- `{hint}`" for hint in role.sequencing_hints]),
            ]),
        )

    for template in sorted(snapshot.block_templates, key=lambda item: item.template_id):
        _write_note(
            blocks_dir / f"{template.template_id}.md",
            {
                "type": "block_template",
                "source_of_truth": "db",
                "kg_version": snapshot.version_label,
                "template_id": template.template_id,
                "goal": template.goal,
                "phase": template.phase,
                "duration_weeks": template.duration_weeks,
                "days_per_week": template.days_per_week,
                "season_context": template.season_context,
                "periodization_model": template.periodization_model,
                "session_role_ids": template.session_role_ids,
            },
            "\n".join([
                f"# {template.template_id}",
                "",
                f"- Goal: `{template.goal}`",
                f"- Phase: `{template.phase}`",
                f"- Duration: `{template.duration_weeks}` weeks",
                f"- Days/week: `{template.days_per_week}`",
                f"- Season context: `{template.season_context}`",
                "",
                "## Session Roles",
                *[f"- [[session_roles/{role_id}|{role_id}]]" for role_id in template.session_role_ids],
            ]),
        )

    for template in snapshot.progression_templates:
        template_name = f"{template.family_id}__{template.session_role}__{template.goal_phase}__{template.training_level}"
        _write_note(
            progressions_dir / f"{template_name}.md",
            {
                "type": "progression_template",
                "source_of_truth": "db",
                "kg_version": snapshot.version_label,
                "family_id": template.family_id,
                "session_role": template.session_role,
                "goal_phase": template.goal_phase,
                "training_level": template.training_level,
                "default_sets_by_week": template.default_sets_by_week,
                "rep_range": list(template.rep_range),
                "target_rpe_range": list(template.target_rpe_range),
                "anchor_duration_weeks": template.anchor_duration_weeks,
            },
            "\n".join([
                f"# {template_name}",
                "",
                f"- Family: [[families/{template.family_id}|{template.family_id}]]",
                f"- Session role: `{template.session_role}`",
                f"- Goal phase: `{template.goal_phase}`",
                f"- Training level: `{template.training_level}`",
            ]),
        )

    for rule in snapshot.constraint_rules:
        _write_note(
            constraints_dir / f"{rule.rule_id}.md",
            {
                "type": "constraint_rule",
                "source_of_truth": "db",
                "kg_version": snapshot.version_label,
                "rule_id": rule.rule_id,
                "rule_type": rule.rule_type,
                "subject_type": rule.subject_type,
                "subject_key": rule.subject_key,
                "config": rule.config,
            },
            "\n".join([
                f"# {rule.rule_id}",
                "",
                f"- Rule type: `{rule.rule_type}`",
                f"- Subject: `{rule.subject_type}` / `{rule.subject_key}`",
                "",
                "```json",
                json.dumps(rule.config, indent=2, sort_keys=True),
                "```",
            ]),
        )

    _write_note(
        output_dir / "KG_Index.md",
        {
            "type": "kg_index",
            "source_of_truth": "db",
            "kg_version": snapshot.version_label,
        },
        "\n".join([
            "# V7 Knowledge Graph",
            "",
            "DB remains the source of truth. This vault is an exported browse/edit surface.",
            "",
            f"- Version: `{snapshot.version_label}`",
            f"- Exercises: `{len(snapshot.exercises)}`",
            f"- Families: `{len(family_map)}`",
            f"- Session roles: `{len(snapshot.session_roles)}`",
            "",
            "## Maps",
            "- [[canvases/exercise_families.canvas]]",
            "- [[canvases/session_roles.canvas]]",
            "- [[canvases/block_templates.canvas]]",
        ]),
    )

    _write_canvas(
        canvases_dir / "exercise_families.canvas",
        [
            {"id": family_id, "label": family_id, "file": f"families/{family_id}.md"}
            for family_id in sorted(family_map.keys())[:40]
        ],
    )
    _write_canvas(
        canvases_dir / "session_roles.canvas",
        [
            {"id": role_id, "label": role.label, "file": f"session_roles/{role_id}.md"}
            for role_id, role in sorted(snapshot.session_roles.items())[:40]
        ],
    )
    _write_canvas(
        canvases_dir / "block_templates.canvas",
        [
            {"id": template.template_id, "label": template.template_id, "file": f"block_templates/{template.template_id}.md"}
            for template in snapshot.block_templates[:40]
        ],
    )

    return output_dir


def _load_snapshot():
    try:
        with get_db_session() as db:
            return ensure_active_kg_snapshot(db)
    except Exception:
        return build_fallback_snapshot()


def _write_note(path: Path, frontmatter: dict, body: str) -> None:
    frontmatter_text = _to_frontmatter(frontmatter)
    path.write_text(f"---\n{frontmatter_text}---\n\n{body}\n", encoding="utf-8")


def _to_frontmatter(data: dict) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {_yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def _yaml_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace('"', '\\"')
        return f"\"{escaped}\""
    return json.dumps(value, sort_keys=True)


def _write_canvas(path: Path, items: list[dict]) -> None:
    nodes = []
    edges = []
    for index, item in enumerate(items):
        x = (index % 4) * 340
        y = (index // 4) * 220
        nodes.append({
            "id": item["id"],
            "type": "file",
            "file": item["file"],
            "x": x,
            "y": y,
            "width": 300,
            "height": 160,
        })
        if index > 0:
            edges.append({
                "id": f"edge_{index}",
                "fromNode": items[index - 1]["id"],
                "toNode": item["id"],
            })
    path.write_text(json.dumps({"nodes": nodes, "edges": edges}, indent=2), encoding="utf-8")


def _list_or_none(items: list[str]) -> list[str]:
    return items or ["- None"]


if __name__ == "__main__":
    output = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else DEFAULT_OUTPUT
    exported = export_obsidian_vault(output)
    print(f"Exported Obsidian vault snapshot to {exported}")
