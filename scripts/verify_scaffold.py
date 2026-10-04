"""Validate the foundation without installing dependencies or creating health data."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "CODEX.md",
    ".env.example",
    ".gitignore",
    "docker-compose.yml",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
    ".github/workflows/ci.yml",
    "docs/project-brief.md",
    "docs/ux/ux-design.md",
    "docs/architecture/architecture.md",
    "docs/architecture/repo-architecture.md",
    "docs/data/data-model.md",
    "docs/ai/personal-ai-integration.md",
    "docs/security/security-privacy.md",
    "docs/deployment/technology-deployment.md",
    "docs/api/api-contract.md",
    "docs/local-development.md",
    "docs/implementation/implementation-plan.md",
    "docs/implementation/web-extension-plan.md",
    "docs/web/web-extension-architecture.md",
    "docs/handoff/codex-handoff.md",
    "docs/handoff/phase-plan-authoring-standard.md",
    "apps/mobile/package.json",
    "apps/mobile/app.json",
    "apps/mobile/tsconfig.json",
    "apps/mobile/app/_layout.tsx",
    "apps/mobile/app/index.tsx",
    "apps/mobile/tests/README.md",
    "services/api/pyproject.toml",
    "services/api/requirements-dev.lock",
    "services/api/src/health_api/main.py",
    "services/api/tests/test_smoke.py",
    "packages/api-client/package.json",
    "packages/api-client/README.md",
    "packages/domain/README.md",
    "packages/design-tokens/README.md",
    "packages/shared/README.md",
    "contracts/openapi/README.md",
    "contracts/schemas/README.md",
    "migrations/README.md",
)


def main() -> None:
    errors = [f"Missing scaffold file: {path}" for path in REQUIRED if not (ROOT / path).is_file()]
    for manifest_path in (
        "package.json",
        "apps/mobile/package.json",
        "packages/api-client/package.json",
        "apps/mobile/app.json",
        "apps/mobile/tsconfig.json",
    ):
        try:
            json.loads((ROOT / manifest_path).read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"Invalid JSON {manifest_path}: {exc}")
    try:
        tomllib.loads((ROOT / "services/api/pyproject.toml").read_text())
    except (OSError, ValueError) as exc:
        errors.append(f"Invalid API manifest: {exc}")
    for source in (
        ROOT / "services/api/src",
        ROOT / "apps/mobile/src",
        ROOT / "apps/mobile/app",
    ):
        for path in source.rglob("*"):
            if path.is_file() and (
                path.name.startswith("test_") or ".test." in path.name or ".spec." in path.name
            ):
                errors.append(f"Test in production source: {path.relative_to(ROOT)}")
    for package in (ROOT / "packages").iterdir():
        manifest = package / "package.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            dependencies = {
                **data.get("dependencies", {}),
                **data.get("peerDependencies", {}),
            }
            if any(name.startswith(("react-native", "expo")) for name in dependencies):
                errors.append(f"Native dependency in shared frontend package: {manifest}")
        for path in package.rglob("*"):
            if "node_modules" in path.parts or path.suffix not in {
                ".ts",
                ".tsx",
                ".js",
            }:
                continue
            if re.search(
                r"(?:from\s*|require\s*\(\s*|import\s*\(\s*)['\"](?:expo|react-native)",
                path.read_text(),
            ):
                errors.append(f"Native import in shared frontend source: {path.relative_to(ROOT)}")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Scaffold verification passed (files, manifests, source/test and native boundaries).")


if __name__ == "__main__":
    main()
