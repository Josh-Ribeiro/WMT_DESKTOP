from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RepositoryHygieneTests(unittest.TestCase):
    def test_application_versions_are_synchronized(self) -> None:
        package_version = json.loads(
            (ROOT / "package.json").read_text(encoding="utf-8")
        )["version"]
        tauri_version = json.loads(
            (ROOT / "src-tauri" / "tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )["version"]
        cargo_source = (ROOT / "src-tauri" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
        backend_source = (
            ROOT / "backend" / "app" / "core" / "config.py"
        ).read_text(encoding="utf-8")
        cargo_version = re.search(
            r'(?m)^version\s*=\s*"([^"]+)"',
            cargo_source,
        )
        backend_version = re.search(
            r'APP_VERSION = os\.getenv\("WMT_VERSION", "([^"]+)"\)',
            backend_source,
        )

        self.assertIsNotNone(cargo_version)
        self.assertIsNotNone(backend_version)
        self.assertEqual(
            {package_version},
            {
                tauri_version,
                cargo_version.group(1),
                backend_version.group(1),
            },
        )

    def test_release_runs_the_automated_quality_gate(self) -> None:
        release_script = (
            ROOT / "scripts" / "build-and-release.ps1"
        ).read_text(encoding="utf-8-sig")
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertIn("verify", package["scripts"])
        self.assertIn("format:check", package["scripts"])
        self.assertIn('verify.ps1"', release_script)
        self.assertTrue((ROOT / ".github" / "workflows" / "verify.yml").is_file())

    def test_historical_wix_sdk_is_not_versioned_in_the_source_tree(self) -> None:
        self.assertFalse((ROOT / "src-tauri" / "WinxTools").exists())

    def test_unused_runtime_dependencies_are_absent(self) -> None:
        python_requirements = (
            ROOT / "backend" / "requirements.txt"
        ).read_text(encoding="utf-8")
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        frontend_dependencies = {
            *package.get("dependencies", {}),
            *package.get("devDependencies", {}),
        }

        for dependency in {
            "python-multipart",
            "pydantic-settings",
            "pyodbc",
            "python-jose",
            "passlib",
            "python-dotenv",
            "requests",
            "httpx",
            "pyyaml",
        }:
            self.assertNotIn(dependency, python_requirements.lower())

        self.assertTrue(
            {
                "@radix-ui/react-dropdown-menu",
                "@tailwindcss/typography",
                "autoprefixer",
                "pnpm",
                "postcss",
                "tailwindcss-animate",
                "tsx",
            }.isdisjoint(frontend_dependencies)
        )

    def test_local_markdown_links_resolve(self) -> None:
        markdown_files = [
            *ROOT.glob("*.md"),
            *(ROOT / "docs").glob("*.md"),
        ]
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")

        broken: list[str] = []
        for source in markdown_files:
            for target in link_pattern.findall(
                source.read_text(encoding="utf-8-sig")
            ):
                resolved = (source.parent / target).resolve()
                if not resolved.is_file():
                    broken.append(f"{source.relative_to(ROOT)} -> {target}")

        self.assertEqual([], broken)


if __name__ == "__main__":
    unittest.main()
