"""
Skills Registry — load/discover/execute Claude Code Skills.

WHAT I DO:
  - Walk a skills_dir, parse SKILL.md frontmatter (agentskills.io standard)
  - Validate input against assets/input_schema.json (if present)
  - Execute scripts/run.py and validate output against assets/output_schema.json
  - Return structured ExecutionResult with status + data + warnings

WHAT I DON'T DO:
  - I don't call LLMs (skills do, via their own scripts)
  - I don't publish to Skills Hub
  - I don't version-control SKILL.md contents

IO CONTRACT:
  SkillsRegistry(skills_dir).discover(query) → list[Skill]
  SkillsRegistry(skills_dir).load(name) → Skill
  SkillsRegistry(skills_dir).execute(name, inputs) → ExecutionResult

  Skill: name, description, instructions, input_schema, output_schema, scripts_dir
  ExecutionResult: success, output, validated, warnings, duration_ms

HIDDEN FACTS:
  - Frontmatter parsing: PyYAML if available, else minimal regex parser (degraded)
  - Schema validation: jsonschema if available, else basic key/type check
  - Skill scripts: invoked as `python -m <pkg>` if scripts/run.py exists
  - All loaded Skills cached by name+mtime; reload on file change

DECOUPLING:
  - Pure file IO + subprocess; no LLM dependency
  - Optional jsonschema dep (graceful fallback)
  - Doesn't import from packages/* (would create cycle since skills use packages)
"""

from .registry import (
    SkillsRegistry,
    Skill, ExecutionResult,
    SkillNotFoundError, SkillExecutionError, SchemaError,
)

__all__ = [
    "SkillsRegistry",
    "Skill", "ExecutionResult",
    "SkillNotFoundError", "SkillExecutionError", "SchemaError",
]
