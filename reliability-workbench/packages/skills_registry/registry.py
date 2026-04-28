"""SkillsRegistry implementation.

Per Gemini critique §6: execute() must validate output against output_schema,
NOT return raw dict that callers must guess shape of.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SkillNotFoundError(Exception):
    pass


class SkillExecutionError(RuntimeError):
    pass


class SchemaError(ValueError):
    pass


@dataclass
class Skill:
    name: str
    description: str
    skill_md_path: Path
    instructions: str                 # SKILL.md body after frontmatter
    scripts_dir: Path | None
    input_schema: dict | None         # parsed from assets/input_schema.json
    output_schema: dict | None
    metadata: dict                    # other frontmatter fields (e.g., agentskills.io extensions)


@dataclass
class ExecutionResult:
    """Output of SkillsRegistry.execute() — structured, validated."""
    success: bool
    output: dict                      # the skill's actual output dict
    validated: bool                   # did output pass output_schema? (False if no schema)
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0
    skill_name: str = ""
    schema_violations: list[str] = field(default_factory=list)


# ──────────────────────────────────────────
# Frontmatter parsing
# ──────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Returns (metadata, body). Metadata is empty dict if no frontmatter."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    try:
        import yaml  # type: ignore
        meta = yaml.safe_load(fm_text) or {}
        if not isinstance(meta, dict):
            return {}, body
        return meta, body
    except ImportError:
        # Minimal fallback: parse `key: value` lines (no nested support)
        meta = {}
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
        return meta, body


# ──────────────────────────────────────────
# Schema validation
# ──────────────────────────────────────────

def _validate_against_schema(data: dict, schema: dict | None) -> list[str]:
    """Returns list of violation strings; empty = OK. None schema = no check (returns [])."""
    if schema is None:
        return []
    try:
        import jsonschema  # type: ignore
        try:
            jsonschema.validate(instance=data, schema=schema)
            return []
        except jsonschema.ValidationError as e:
            return [f"{e.json_path}: {e.message}"]
    except ImportError:
        # Minimal fallback: check required + types at top level
        violations = []
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        for key in required:
            if key not in data:
                violations.append(f"missing required field: {key}")
        for key, value in data.items():
            if key in properties and "type" in properties[key]:
                expected = properties[key]["type"]
                py_types = {
                    "string": str, "integer": int, "number": (int, float),
                    "boolean": bool, "array": list, "object": dict, "null": type(None),
                }
                py_type = py_types.get(expected)
                if py_type and not isinstance(value, py_type):
                    violations.append(f"{key}: expected {expected}, got {type(value).__name__}")
        return violations


# ──────────────────────────────────────────
# Skill loading
# ──────────────────────────────────────────

def _load_skill(skill_dir: Path) -> Skill:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise SkillNotFoundError(f"no SKILL.md at {skill_dir}")
    text = skill_md.read_text()
    metadata, body = _parse_frontmatter(text)

    name = metadata.get("name") or skill_dir.name
    description = metadata.get("description", "")

    scripts_dir = skill_dir / "scripts" if (skill_dir / "scripts").exists() else None
    input_schema_path = skill_dir / "assets" / "input_schema.json"
    output_schema_path = skill_dir / "assets" / "output_schema.json"
    input_schema = json.loads(input_schema_path.read_text()) if input_schema_path.exists() else None
    output_schema = json.loads(output_schema_path.read_text()) if output_schema_path.exists() else None

    return Skill(
        name=name,
        description=description,
        skill_md_path=skill_md,
        instructions=body,
        scripts_dir=scripts_dir,
        input_schema=input_schema,
        output_schema=output_schema,
        metadata={k: v for k, v in metadata.items() if k not in ("name", "description")},
    )


# ──────────────────────────────────────────
# Public API
# ──────────────────────────────────────────

class SkillsRegistry:
    def __init__(self, skills_dir: Path | str = ".claude/skills"):
        self.skills_dir = Path(skills_dir)
        self._cache: dict[str, tuple[float, Skill]] = {}

    def list_all(self) -> list[Skill]:
        """Walk skills_dir; return all valid Skills. Skips _template/ and entries
        that fail to load (each emits its own warning when later .load()ed)."""
        if not self.skills_dir.exists():
            return []
        skills = []
        for entry in sorted(self.skills_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            try:
                skills.append(self.load(entry.name))
            except (SkillNotFoundError, OSError):
                continue
        return skills

    def load(self, name: str) -> Skill:
        skill_dir = self.skills_dir / name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"no skill named {name!r} in {self.skills_dir}")
        # mtime-based cache
        mtime = (skill_dir / "SKILL.md").stat().st_mtime if (skill_dir / "SKILL.md").exists() else 0
        if name in self._cache and self._cache[name][0] == mtime:
            return self._cache[name][1]
        skill = _load_skill(skill_dir)
        self._cache[name] = (mtime, skill)
        return skill

    def discover(self, query: str, *, max_results: int = 10) -> list[Skill]:
        """Naive keyword match against name+description. Future: embedding rerank."""
        all_skills = self.list_all()
        if not query:
            return all_skills[:max_results]
        q_lower = query.lower()
        ranked = []
        for s in all_skills:
            score = 0
            haystack = (s.name + " " + s.description).lower()
            for word in q_lower.split():
                score += haystack.count(word)
            if score > 0:
                ranked.append((score, s))
        ranked.sort(key=lambda x: -x[0])
        return [s for _, s in ranked[:max_results]]

    def execute(self, name: str, inputs: dict) -> ExecutionResult:
        """
        Validate inputs → run scripts/run.py with inputs as JSON stdin → validate output.

        Returns ExecutionResult with success/output/validated/warnings.
        Raises SkillNotFoundError, SkillExecutionError, SchemaError.
        """
        skill = self.load(name)

        # 1. Validate input
        input_violations = _validate_against_schema(inputs, skill.input_schema)
        if input_violations:
            raise SchemaError(f"input invalid: {'; '.join(input_violations)}")

        # 2. Execute
        if skill.scripts_dir is None or not (skill.scripts_dir / "run.py").exists():
            raise SkillExecutionError(f"skill {name!r} has no scripts/run.py — not executable")

        run_script = skill.scripts_dir / "run.py"
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(run_script)],
                input=json.dumps(inputs).encode(),
                capture_output=True, timeout=300,
            )
        except subprocess.TimeoutExpired as e:
            raise SkillExecutionError(f"{name} timed out after 300s") from e

        duration_ms = int((time.time() - t0) * 1000)

        if proc.returncode != 0:
            raise SkillExecutionError(
                f"{name} exited {proc.returncode}: {proc.stderr.decode()[:500]}"
            )

        try:
            output = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise SkillExecutionError(
                f"{name} stdout not valid JSON: {e}\nstdout[:200]={proc.stdout[:200]!r}"
            ) from e

        # 3. Validate output
        warnings: list[str] = []
        violations = _validate_against_schema(output, skill.output_schema)
        validated = not violations
        if violations and skill.output_schema is not None:
            warnings.append(f"output schema violations: {'; '.join(violations)}")

        return ExecutionResult(
            success=True, output=output, validated=validated,
            warnings=warnings, duration_ms=duration_ms,
            skill_name=name, schema_violations=violations,
        )
