from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class ColabCarryOverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        notebook_path = cls.root / "notebooks" / "Thesis_Allocation_Colab.ipynb"
        cls.notebook = json.loads(notebook_path.read_text(encoding="utf-8"))

    def test_notebook_documents_optional_previous_final_assignments(self) -> None:
        markdown = " ".join(
            "\n".join(
                "".join(cell["source"])
                for cell in self.notebook["cells"]
                if cell["cell_type"] == "markdown"
            ).split()
        )
        self.assertIn("`9998`", markdown)
        self.assertIn("**any** of the three preference fields", markdown)
        self.assertIn("`9998 / 9998 / 9998`", markdown)
        self.assertIn("`previous_final_assignments.xlsx`", markdown)
        self.assertIn("previous topic, selected language, daily supervisor, and promotor", markdown)
        self.assertIn("no `9998` in any of the three preference fields", markdown)

    def test_complete_colab_workflow_accepts_optional_carry_over_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            self._write_inputs(source)
            downloaded = self._execute_complete_workflow(source, root / "runtime")

            with zipfile.ZipFile(BytesIO(downloaded)) as archive:
                final = pd.read_excel(BytesIO(archive.read("final_assignments.xlsx")))
                report = json.loads(archive.read("run_report.json").decode("utf-8"))

            carried = final.set_index("email").loc["carry@example.org"]
            self.assertEqual(carried["preference_1"], "new-topic")
            self.assertEqual(str(carried["preference_2"]), "9998")
            self.assertEqual(carried["preference_3"], "new-topic")
            self.assertEqual(carried["assigned_topic_id"], "old-topic")
            self.assertEqual(carried["assigned_topic"], "Previous-year thesis")
            self.assertEqual(carried["assigned_language"], "English")
            self.assertEqual(carried["daily_supervisor_email"], "daily@example.org")
            self.assertEqual(carried["promotor_email"], "promotor@example.org")
            self.assertEqual(carried["daily_supervisor_assignment_source"], "carry_over")
            self.assertEqual(carried["promotor_assignment_source"], "carry_over")
            self.assertEqual(report["carry_over_students"], 1)
            self.assertEqual(report["preference_cost"], 0)

    def _execute_complete_workflow(
        self,
        source_directory: Path,
        runtime_root: Path,
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
            "matching_method": "Lexical matching (fast)",
            "retrieve_researcher_profiles": False,
            "allow_partial_results": False,
            "allow_same_person_for_both_roles": False,
            "duplicate_student_submissions": "Keep last submission",
            "reassignment_role": "Daily supervisor",
            "reassignment_scope": "One student",
            "student_email": "",
            "departing_researcher_email": "",
        }

        with (
            patch.dict(
                sys.modules,
                {"google": google_module, "google.colab": colab_module},
            ),
            patch.dict(os.environ, {"COLAB_RUNTIME_ROOT": str(runtime_root)}),
        ):
            exec(compile(source, "colab-run-cell", "exec"), namespace)

        self.assertIsNotNone(FakeFiles.downloaded)
        return FakeFiles.downloaded

    @staticmethod
    def _write_inputs(directory: Path) -> None:
        pd.DataFrame(
            [
                {
                    "full_name": "Daily Supervisor",
                    "email": "daily@example.org",
                    "supervision_languages": "English",
                    "profile_description": "competition regulation",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 0,
                },
                {
                    "full_name": "Promotor",
                    "email": "promotor@example.org",
                    "supervision_languages": "English",
                    "profile_description": "competition regulation",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 0,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
            ]
        ).to_excel(directory / "researchers.xlsx", index=False)

        pd.DataFrame(
            [
                {
                    "topic_id": "new-topic",
                    "topic_title": "New topic",
                    "topic_description": "new current-year topic",
                    "capacity": 1,
                }
            ]
        ).to_excel(directory / "topics.xlsx", index=False)

        pd.DataFrame(
            [
                {
                    "full_name": "Carry Student",
                    "email": "carry@example.org",
                    "preference_1": "new-topic",
                    "preference_1_languages": "English",
                    "preference_2": 9998,
                    "preference_2_languages": "",
                    "preference_3": "new-topic",
                    "preference_3_languages": "English",
                }
            ]
        ).to_excel(directory / "student_preferences.xlsx", index=False)

        pd.DataFrame(
            [
                {
                    "full_name": "Carry Student",
                    "email": "carry@example.org",
                    "assigned_topic_id": "old-topic",
                    "assigned_topic": "Previous-year thesis",
                    "assigned_language": "English",
                    "daily_supervisor": "Daily Supervisor",
                    "daily_supervisor_email": "daily@example.org",
                    "promotor": "Promotor",
                    "promotor_email": "promotor@example.org",
                }
            ]
        ).to_excel(directory / "previous_final_assignments.xlsx", index=False)


if __name__ == "__main__":
    unittest.main()