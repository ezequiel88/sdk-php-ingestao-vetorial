from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


VALID_BUMPS = {"patch": 0, "minor": 1, "major": 2}
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
BASELINE_VERSION_FILE = ".release-base-version"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(version.strip())
    if not match:
        raise ValueError(f"Invalid semantic version: {version}")
    return tuple(int(group) for group in match.groups())


def bump_version(current_version: str, bump: str) -> str:
    major, minor, patch = ensure_semver(current_version)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump type: {bump}")


def read_current_version(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "tag", "--list", "v*.*.*"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    versions: list[tuple[int, int, int]] = []
    for line in result.stdout.splitlines():
        tag = line.strip()
        if not tag:
            continue
        match = TAG_RE.match(tag)
        if not match:
            continue
        versions.append(tuple(int(group) for group in match.groups()))
    if versions:
        latest = max(versions)
        return f"{latest[0]}.{latest[1]}.{latest[2]}"
    baseline_path = repo_root / BASELINE_VERSION_FILE
    if baseline_path.exists():
        baseline = baseline_path.read_text(encoding="utf-8").strip()
        ensure_semver(baseline)
        return baseline
    return "0.0.0"


def parse_front_matter(path: Path) -> tuple[str, str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"Changeset {path} must start with YAML front matter")
    marker = "\n---\n"
    end = content.find(marker, 4)
    if end == -1:
        raise ValueError(f"Changeset {path} must contain a closing front matter marker")
    metadata_block = content[4:end]
    body = content[end + len(marker) :].strip()
    bump: str | None = None
    for raw_line in metadata_block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Invalid changeset line in {path}: {raw_line}")
        metadata_key = key.strip().strip("\"'")
        metadata_value = value.strip().strip("\"'")
        if metadata_key != "php":
            raise ValueError(f"Unknown release target '{metadata_key}' in {path}; expected only 'php'")
        if metadata_value not in VALID_BUMPS:
            raise ValueError(f"Invalid bump '{metadata_value}' in {path}; expected patch, minor or major")
        bump = metadata_value
    if bump is None:
        raise ValueError(f"Changeset {path} does not declare a php bump")
    return bump, body


def load_changesets(repo_root: Path, changeset_dir: Path) -> list[dict[str, str]]:
    absolute_dir = repo_root / changeset_dir
    if not absolute_dir.exists():
        return []
    changesets: list[dict[str, str]] = []
    for path in sorted(absolute_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        bump, body = parse_front_matter(path)
        changesets.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "bump": bump,
                "summary": body,
            }
        )
    return changesets


def aggregate_bump(changesets: list[dict[str, str]]) -> str | None:
    current: str | None = None
    for changeset in changesets:
        bump = changeset["bump"]
        if current is None or VALID_BUMPS[bump] > VALID_BUMPS[current]:
            current = bump
    return current


def build_plan(repo_root: Path, changeset_dir: Path) -> dict[str, object]:
    changesets = load_changesets(repo_root, changeset_dir)
    bump = aggregate_bump(changesets)
    releases: list[dict[str, str]] = []
    if bump is not None:
        current_version = read_current_version(repo_root)
        next_version = bump_version(current_version, bump)
        releases.append(
            {
                "sdk": "php",
                "bump": bump,
                "current_version": current_version,
                "next_version": next_version,
                "tag": f"v{next_version}",
                "manifest": "composer.json",
            }
        )
    return {"changesets": changesets, "releases": releases, "has_releases": bool(releases)}


def write_plan(plan: dict[str, object], output_path: Path) -> None:
    output_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def load_plan(plan_path: Path) -> dict[str, object]:
    return json.loads(plan_path.read_text(encoding="utf-8"))


def print_github_outputs(plan: dict[str, object]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise RuntimeError("GITHUB_OUTPUT is not set")
    releases = plan["releases"]
    assert isinstance(releases, list)
    tags = ",".join(release["tag"] for release in releases)
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"has_releases={'true' if releases else 'false'}\n")
        handle.write(f"release_count={len(releases)}\n")
        handle.write(f"release_tags={tags}\n")


def apply_plan(repo_root: Path, plan_path: Path) -> None:
    plan = load_plan(plan_path)
    changesets = plan["changesets"]
    assert isinstance(changesets, list)
    for changeset in changesets:
        relative_path = changeset["path"]
        assert isinstance(relative_path, str)
        (repo_root / relative_path).unlink(missing_ok=False)


def print_tags(plan_path: Path) -> None:
    plan = load_plan(plan_path)
    releases = plan["releases"]
    assert isinstance(releases, list)
    for release in releases:
        print(release["tag"])


def is_release_relevant_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith(".changeset/"):
        return False
    if normalized.startswith("vendor/"):
        return False
    if normalized in {"README.md", ".gitignore", ".phpunit.result.cache"}:
        return False
    return normalized.startswith("src/") or normalized.startswith("tests/") or normalized in {
        "composer.json",
        "phpstan.neon",
        "phpunit.xml",
    }


def changed_files(repo_root: Path, base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def require_changeset(repo_root: Path, base_ref: str) -> int:
    files = changed_files(repo_root, base_ref)
    has_release_changes = any(is_release_relevant_path(path) for path in files)
    has_changeset = any(
        path.startswith(".changeset/") and path.endswith(".md") and not path.lower().endswith("readme.md")
        for path in files
    )
    if has_release_changes and not has_changeset:
        print("PHP SDK changes detected without a changeset file in .changeset/.", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PHP SDK release helpers")
    parser.add_argument("--repo-root", default=str(repo_root_from_script()))
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="Generate the pending release plan")
    plan_parser.add_argument("--changeset-dir", default=".changeset")
    plan_parser.add_argument("--output-json")
    plan_parser.add_argument("--github-output", action="store_true")
    apply_parser = subparsers.add_parser("apply", help="Apply a release plan")
    apply_parser.add_argument("--plan-file", required=True)
    print_tags_parser = subparsers.add_parser("print-tags", help="Print release tags from a plan")
    print_tags_parser.add_argument("--plan-file", required=True)
    require_parser = subparsers.add_parser("require-changeset", help="Fail if release changes are missing a changeset")
    require_parser.add_argument("--diff-base", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        if args.command == "plan":
            plan = build_plan(repo_root, Path(args.changeset_dir))
            if args.output_json:
                write_plan(plan, repo_root / args.output_json)
            else:
                print(json.dumps(plan, indent=2))
            if args.github_output:
                print_github_outputs(plan)
            return 0
        if args.command == "apply":
            apply_plan(repo_root, repo_root / args.plan_file)
            return 0
        if args.command == "print-tags":
            print_tags(repo_root / args.plan_file)
            return 0
        if args.command == "require-changeset":
            return require_changeset(repo_root, args.diff_base)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())