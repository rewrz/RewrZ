from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "__pycache__",
    "node_modules",
    "media_uploads",
    "data",
    "release",
    "dist",
    "htmlcov",
}

EXCLUDED_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.log",
    "tmp_*",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="根据当前工作区生成干净的 RewrZ 发布包（ZIP）。"
    )
    parser.add_argument(
        "--version",
        help="发布包版本号；未提供时自动按日期和提交短哈希生成。",
    )
    parser.add_argument(
        "--output-dir",
        default="release",
        help="输出目录，默认：release",
    )
    parser.add_argument(
        "--name-prefix",
        default="RewrZ",
        help="发布包名前缀，默认：RewrZ",
    )
    return parser


def run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def resolve_version(repo_root: Path, raw_version: str | None) -> str:
    if raw_version:
        return raw_version.strip()

    short_sha = run_git(repo_root, "rev-parse", "--short", "HEAD")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{timestamp}-{short_sha}"


def list_tracked_files(repo_root: Path) -> list[Path]:
    output = run_git(repo_root, "ls-files", "-z")
    if not output:
        return []

    files: list[Path] = []
    for item in output.split("\0"):
        if not item:
            continue
        files.append(repo_root / Path(item))
    return files


def should_exclude(repo_root: Path, file_path: Path) -> bool:
    relative = file_path.relative_to(repo_root)
    parts = relative.parts

    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True

    path_text = relative.as_posix()
    file_name = relative.name

    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(path_text, pattern):
            return True

    return False


def package_files(
    repo_root: Path,
    files: list[Path],
    output_zip: Path,
    package_root_name: str,
) -> int:
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for file_path in files:
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(repo_root)
            archive_name = Path(package_root_name) / relative
            archive.write(file_path, archive_name.as_posix())
            count += 1
    return count


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    version = resolve_version(repo_root, args.version)
    safe_version = version.replace("/", "-").replace("\\", "-").replace(" ", "-")
    package_root_name = f"{args.name_prefix}-{safe_version}"
    output_dir = (repo_root / args.output_dir).resolve()
    output_zip = output_dir / f"{package_root_name}.zip"

    try:
        tracked_files = list_tracked_files(repo_root)
    except subprocess.CalledProcessError as exc:
        print("发布包生成失败：无法读取 Git 跟踪文件列表。", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return 1

    included_files = [
        file_path
        for file_path in tracked_files
        if not should_exclude(repo_root, file_path)
    ]

    if not included_files:
        print("发布包生成失败：没有可打包的文件。", file=sys.stderr)
        return 1

    file_count = package_files(repo_root, included_files, output_zip, package_root_name)

    print(f"发布包已生成：{output_zip}")
    print(f"包内根目录：{package_root_name}/")
    print(f"打包文件数：{file_count}")
    print("说明：仅打包 Git 已跟踪文件，并自动排除本地环境与缓存产物。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
