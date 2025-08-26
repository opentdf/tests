"""Evidence management for test execution."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from .models import Evidence, TestStatus, TestCase

logger = logging.getLogger(__name__)


class ArtifactManager:
    """Manages test artifacts storage."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, evidence: Evidence) -> Path:
        """
        Store evidence JSON file.

        Returns:
            Path to the stored evidence file.
        """
        evidence_dir = self.base_dir / evidence.profile_id / evidence.variant
        evidence_dir.mkdir(parents=True, exist_ok=True)

        file_path = evidence_dir / f"{evidence.test_name.replace(' ', '_')}_evidence.json"
        with open(file_path, "w") as f:
            json.dump(evidence.to_json_dict(), f, indent=2)
        
        logger.debug(f"Evidence for {evidence.test_name} stored at {file_path}")
        return file_path


class EvidenceManager:
    """Manages evidence collection and artifact generation."""

    def __init__(self, artifact_manager: ArtifactManager):
        self.artifact_manager = artifact_manager

    def collect_evidence(
        self,
        test_case: TestCase,
        profile_id: str,
        variant: str,
        status: TestStatus,
        start_time: datetime,
        end_time: datetime,
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ) -> Evidence:
        """
        Collect evidence for a test execution.

        Args:
            test_case: The test case that was executed.
            profile_id: The ID of the profile used.
            variant: The test variant executed.
            status: The final status of the test.
            start_time: The start time of the test execution.
            end_time: The end time of the test execution.
            error_message: The error message if the test failed.
            error_traceback: The error traceback if the test failed.

        Returns:
            The collected evidence object.
        """
        duration = (end_time - start_time).total_seconds()

        evidence = Evidence(
            req_id=test_case.requirement_id,
            profile_id=profile_id,
            variant=variant,
            commit_sha=self._get_commit_sha(),
            start_timestamp=start_time,
            end_timestamp=end_time,
            status=status,
            duration_seconds=duration,
            test_name=test_case.name,
            test_file=test_case.file_path,
            capabilities_tested=test_case.required_capabilities,
            tags=list(test_case.tags),
            error_message=error_message,
            error_traceback=error_traceback,
        )

        # Store the evidence artifact
        artifact_path = self.artifact_manager.store(evidence)
        evidence.artifact_url = str(artifact_path)

        return evidence

    def _get_commit_sha(self) -> Optional[str]:
        """Get the current git commit SHA."""
        try:
            import subprocess
            commit_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).parent.parent.parent,
                encoding='utf-8'
            ).strip()
            return commit_sha
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Could not determine git commit SHA.")
            return None
