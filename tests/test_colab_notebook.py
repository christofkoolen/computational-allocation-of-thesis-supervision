from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class ColabNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.notebook_path = cls.root / "notebooks" / "Thesis_Allocation_Colab.ipynb"
        cls.notebook = json.loads(cls.notebook_path.read_text(encoding="utf-8"))

    def test_notebook_is_current(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts" / "build_colab_notebook.py"),
                "--check",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_numbered_sections_are_in_requested_order(self) -> None:
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in self.notebook["cells"]
            if cell["cell_type"] == "markdown"
        )
        first = markdown.index("## 1. Optional: download blank input files")
        second = markdown.index("## 2. Choose a workflow")
        workflow_one = markdown.index(
            "### 2.a Workflow 1: thesis topic and supervision allocation"
        )
        workflow_two = markdown.index("### 2.b Workflow 2: reassignment")
        third = markdown.index("## 3. Run the selected workflow")
        self.assertLess(first, second)
        self.assertLess(second, workflow_one)
        self.assertLess(workflow_one, workflow_two)
        self.assertLess(workflow_two, third)
        self.assertIn("skip section 1", markdown.casefold())

    def test_notebook_explains_own_topic_and_reassignment_email_fields(self) -> None:
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in self.notebook["cells"]
            if cell["cell_type"] == "markdown"
        )
        self.assertIn("ranking `9999` first", markdown)
        self.assertIn("`student_email`", markdown)
        self.assertIn("`departing_researcher_email`", markdown)

    def test_template_columns_keep_languages_on_researchers(self) -> None:
        template_cell = next(
            cell
            for cell in self.notebook["cells"]
            if cell.get("metadata", {}).get("id") == "templates"
        )
        source = "".join(template_cell["source"])
        researcher_block, remainder = source.split('"topics.xlsx":', maxsplit=1)
        topic_block = remainder.split('"student_preferences.xlsx":', maxsplit=1)[0]
        self.assertIn('"supervision_languages"', researcher_block)
        self.assertNotIn('"supervision_languages"', topic_block)

    def test_notebook_contains_no_saved_outputs_and_code_compiles(self) -> None:
        code_cells = [
            cell for cell in self.notebook["cells"] if cell["cell_type"] == "code"
        ]
        self.assertGreaterEqual(len(code_cells), 5)
        for cell in code_cells:
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
            source = "".join(cell["source"])
            compile(source, f"{self.notebook_path}:{cell['metadata']['id']}", "exec")

    def test_notebook_uses_public_package_without_drive_mount(self) -> None:
        code = "\n".join(
            "".join(cell["source"])
            for cell in self.notebook["cells"]
            if cell["cell_type"] == "code"
        )
        self.assertIn('"git+https://github.com/christofkoolen/"', code)
        self.assertIn(
            '"computational-allocation-of-thesis-supervision.git@main"',
            code,
        )
        self.assertIn("files.upload()", code)
        self.assertIn("files.download(", code)
        self.assertNotIn("drive.mount", code)

    def test_complete_notebook_workflow_produces_results_zip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_directory = root / "source"
            source_directory.mkdir()
            self._write_example_inputs(source_directory)
            downloaded = self._execute_workflow(
                source_directory,
                root / "runtime",
                task="Complete allocation",
            )
            with zipfile.ZipFile(self._bytes_file(downloaded)) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "final_assignments.xlsx",
                        "final_assignments_shareable.xlsx",
                        "researchers_enriched.xlsx",
                        "run_report.json",
                        "supervisor_summary.xlsx",
                        "topic_assignments.xlsx",
                    },
                )

    def test_reassignment_notebook_workflow_produces_results_zip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_directory = root / "source"
            source_directory.mkdir()
            self._write_reassignment_inputs(source_directory)
            downloaded = self._execute_workflow(
                source_directory,
                root / "runtime",
                task="Reassign supervision",
                reassignment_role="Daily supervisor",
                reassignment_scope="One student",
                student_email="student@example.org",
            )
            with zipfile.ZipFile(self._bytes_file(downloaded)) as archive:
                log = pd.read_csv(
                    self._bytes_file(archive.read("reassignment_log.csv"))
                )
            self.assertEqual(
                log.iloc[0]["new_supervisor_email"],
                "charlie@example.org",
            )

    def _execute_workflow(
        self,
        source_directory: Path,
        runtime_root: Path,
        **overrides: object,
    ) -> bytes:
        run_cell = next(
            cell
            for cell in self.notebook["cells"]
            if cell.get("metadata", {}).get("id") == "run"
        )
        source = "".join(run_cell["source"])

        class FakeFiles:
            downloaded: bytes | None = None

            @staticmethod
            def upload() -> dict[str, bytes]:
                uploaded = {}
                for path in source_directory.iterdir():
                    destination = Path.cwd() / path.name
                    shutil.copyfile(path, destination)
                    uploaded[path.name] = path.read_bytes()
                return uploaded

            @classmethod
            def download(cls, path: str) -> None:
                cls.downloaded = Path(path).read_bytes()

        google_module = types.ModuleType("google")
        colab_module = types.ModuleType("google.colab")
        colab_module.files = FakeFiles
        google_module.colab = colab_module
        namespace = {
            "task": "Complete allocation",
            "matching_method": "Fast lexical matching",
            "retrieve_researcher_profiles": False,
            "allow_partial_results": False,
            "allow_same_person_for_both_roles": False,
            "duplicate_student_submissions": "Keep last submission",
            "reassignment_role": "Daily supervisor",
            "reassignment_scope": "One student",
            "student_email": "",
            "departing_researcher_email": "",
            **overrides,
        }

        with (
            patch.dict(
                sys.modules,
                {"google": google_module, "google.colab": colab_module},
            ),
            patch.dict(
                os.environ,
                {"COLAB_RUNTIME_ROOT": str(runtime_root)},
            ),
        ):
            exec(compile(source, "colab-run-cell", "exec"), namespace)

        self.assertIsNotNone(FakeFiles.downloaded)
        return FakeFiles.downloaded

    @staticmethod
    def _bytes_file(content: bytes):
        from io import BytesIO

        return BytesIO(content)

    @staticmethod
    def _write_example_inputs(directory: Path) -> None:
        pd.DataFrame(
            [
                {
                    "full_name": "Alice",
                    "email": "alice@example.org",
                    "profile_description": "privacy law safeguards",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
                {
                    "full_name": "Bob",
                    "email": "bob@example.org",
                    "profile_description": "data engineering systems",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
            ]
        ).to_excel(directory / "people.xlsx", index=False)
        pd.DataFrame(
            [
                {
                    "topic_id": "privacy",
                    "topic_title": "Privacy law",
                    "topic_description": "privacy rights safeguards",
                    "capacity": 1,
                },
                {
                    "topic_id": "data",
                    "topic_title": "Data engineering",
                    "topic_description": "data engineering systems",
                    "capacity": 1,
                },
                {
                    "topic_id": "contracts",
                    "topic_title": "Contract law",
                    "topic_description": "commercial contracts",
                    "capacity": 1,
                },
            ]
        ).to_excel(directory / "subjects.xlsx", index=False)
        pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "privacy",
                    "preference_2": "data",
                    "preference_3": "contracts",
                }
            ]
        ).to_excel(directory / "choices.xlsx", index=False)

    @staticmethod
    def _write_reassignment_inputs(directory: Path) -> None:
        pd.DataFrame(
            [
                {
                    "full_name": "Alice",
                    "email": "alice@example.org",
                    "profile_description": "privacy law safeguards",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
                {
                    "full_name": "Bob",
                    "email": "bob@example.org",
                    "profile_description": "data engineering systems",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 0,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
                {
                    "full_name": "Charlie",
                    "email": "charlie@example.org",
                    "profile_description": "privacy rights safeguards",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 0,
                },
            ]
        ).to_excel(directory / "people.xlsx", index=False)
        pd.DataFrame(
            [
                {
                    "topic_id": "privacy",
                    "topic_title": "Privacy law",
                    "topic_description": "privacy rights safeguards",
                    "capacity": 1,
                }
            ]
        ).to_excel(directory / "subjects.xlsx", index=False)
        pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                    "daily_supervisor": "Alice",
                    "daily_supervisor_email": "alice@example.org",
                    "promotor": "Bob",
                    "promotor_email": "bob@example.org",
                }
            ]
        ).to_excel(directory / "previous_assignments.xlsx", index=False)


if __name__ == "__main__":
    unittest.main()
