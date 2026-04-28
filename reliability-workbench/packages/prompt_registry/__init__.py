"""
Prompt Registry — versioned prompts with frontmatter.

WHAT I DO:
  - Store prompts as .md files with YAML frontmatter (id, version, model, parent, accuracy, notes)
  - Auto-version on save: v1, v2, v3... (parent_version forms a tree)
  - Look up by id (latest) or id+version (specific)
  - List versions of a prompt id

WHAT I DON'T DO:
  - I don't render templates (caller does string formatting)
  - I don't call LLMs
  - I don't diff versions (caller shows the diff)
  - I don't enforce A/B testing (caller picks which version to use)

IO CONTRACT:
  PromptRegistry(prompts_dir).get(id, version=None) → Prompt
  PromptRegistry(prompts_dir).save(id, content, model, parent_version=None) → Prompt
  PromptRegistry(prompts_dir).list_versions(id) → list[str]

  Prompt: id, version, content, model, parent_version, created_at, notes, metadata

HIDDEN FACTS:
  - File layout: prompts/<id>/v1.md, v2.md, ...; "latest" symlink optional
  - Versioning: auto-increments to next vN that doesn't exist
  - Caller can pass extra frontmatter via **frontmatter

DECOUPLING:
  - Pure file IO + YAML
  - Doesn't import packages/*
"""

from .registry import (
    PromptRegistry, Prompt,
    PromptNotFoundError, VersionConflict,
)

__all__ = ["PromptRegistry", "Prompt", "PromptNotFoundError", "VersionConflict"]
