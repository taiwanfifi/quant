"""PromptRegistry implementation."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


class PromptNotFoundError(Exception):
    pass


class VersionConflict(Exception):
    pass


@dataclass
class Prompt:
    id: str
    version: str
    content: str                       # body after frontmatter
    model: str
    parent_version: str | None = None
    created_at: float = 0.0
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse(text: str) -> tuple[dict, str]:
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
        meta = {}
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
        return meta, body


def _serialize(meta: dict, content: str) -> str:
    try:
        import yaml  # type: ignore
        fm = yaml.safe_dump(meta, default_flow_style=False, sort_keys=False).strip()
    except ImportError:
        fm = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{fm}\n---\n\n{content}\n"


_VERSION_RE = re.compile(r"^v(\d+)\.md$")


class PromptRegistry:
    def __init__(self, prompts_dir: Path | str = "prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def _id_dir(self, prompt_id: str) -> Path:
        return self.prompts_dir / prompt_id

    def list_versions(self, prompt_id: str) -> list[str]:
        d = self._id_dir(prompt_id)
        if not d.exists():
            return []
        versions = []
        for f in d.iterdir():
            m = _VERSION_RE.match(f.name)
            if m:
                versions.append(f"v{m.group(1)}")
        return sorted(versions, key=lambda v: int(v[1:]))

    def get(self, prompt_id: str, *, version: str | None = None) -> Prompt:
        d = self._id_dir(prompt_id)
        if not d.exists():
            raise PromptNotFoundError(f"no prompt id {prompt_id!r}")
        if version is None:
            versions = self.list_versions(prompt_id)
            if not versions:
                raise PromptNotFoundError(f"prompt {prompt_id!r} has no versions")
            version = versions[-1]
        path = d / f"{version}.md"
        if not path.exists():
            raise PromptNotFoundError(f"no version {version} for prompt {prompt_id!r}")
        meta, body = _parse(path.read_text())
        return Prompt(
            id=prompt_id, version=version, content=body.strip(),
            model=meta.get("model", "unknown"),
            parent_version=meta.get("parent_version"),
            created_at=float(meta.get("created_at", 0)),
            notes=meta.get("notes", ""),
            metadata={k: v for k, v in meta.items()
                      if k not in ("id", "version", "model", "parent_version",
                                    "created_at", "notes")},
        )

    def save(
        self, prompt_id: str, content: str, *,
        model: str,
        parent_version: str | None = None,
        notes: str = "",
        **extra_frontmatter,
    ) -> Prompt:
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$", prompt_id):
            raise ValueError(f"prompt_id must be kebab-case, got {prompt_id!r}")
        d = self._id_dir(prompt_id)
        d.mkdir(exist_ok=True)
        existing = self.list_versions(prompt_id)
        next_n = (int(existing[-1][1:]) + 1) if existing else 1
        version = f"v{next_n}"
        path = d / f"{version}.md"
        if path.exists():
            raise VersionConflict(f"{path} already exists")

        now = time.time()
        meta = {
            "id": prompt_id,
            "version": version,
            "model": model,
            "parent_version": parent_version,
            "created_at": now,
            "notes": notes,
            **extra_frontmatter,
        }
        path.write_text(_serialize(meta, content.strip()))
        return Prompt(
            id=prompt_id, version=version, content=content.strip(),
            model=model, parent_version=parent_version,
            created_at=now, notes=notes,
            metadata=extra_frontmatter,
        )
