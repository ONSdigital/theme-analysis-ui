"""Unit tests for workflow triggering utilities."""

from __future__ import annotations

import json

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch
import pytest

from theme_analysis_ui.utils.workflow_utils import (
    WorkflowConfigError,
    get_workflow_config,
    trigger_workflow,
)


class DummyExecution:
    """Fake workflow execution object capturing the provided argument."""

    def __init__(self, *, argument: str) -> None:
        self.argument = argument


class DummyExecutionResponse:
    """Fake workflow execution response."""

    def __init__(self, name: str) -> None:
        self.name = name


class DummyExecutionsClient:
    """Fake Workflows client recording create_execution calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, DummyExecution]] = []

    def create_execution(
        self,
        *,
        parent: str,
        execution: DummyExecution,
    ) -> DummyExecutionResponse:
        """Record the request and return a fake execution response.

        Args:
            parent: Workflow parent resource path.
            execution: Execution payload object.

        Returns:
            Fake execution response.
        """
        self.calls.append((parent, execution))
        return DummyExecutionResponse(
            "projects/demo-project/locations/europe-west2/workflows/demo-workflow/executions/123",
        )


def test_get_workflow_config_returns_values(monkeypatch: MonkeyPatch) -> None:
    """Ensure workflow configuration is loaded from environment variables."""

    monkeypatch.setenv("PROJECT_ID", "demo-project")
    monkeypatch.setenv("WORKFLOW_REGION", "europe-west2")
    monkeypatch.setenv("WORKFLOW_NAME", "demo-workflow")
    monkeypatch.setenv("CR_JOB_NAME", "themes-job")
    monkeypatch.setenv("CR_JOB_REGION", "europe-west2")

    result = get_workflow_config()

    assert result == (  # nosec B101
        "demo-project",
        "europe-west2",
        "demo-workflow",
        "themes-job",
        "europe-west2",
    )


@pytest.mark.parametrize(
    ("missing_key"),
    [
        "PROJECT_ID",
        "WORKFLOW_REGION",
        "WORKFLOW_NAME",
        "CR_JOB_NAME",
        "CR_JOB_REGION",
    ],
)
def test_get_workflow_config_raises_when_variable_missing(
    monkeypatch: MonkeyPatch,
    missing_key: str,
) -> None:
    """Ensure a clear error is raised when required config is missing."""

    env = {
        "PROJECT_ID": "demo-project",
        "WORKFLOW_REGION": "europe-west2",
        "WORKFLOW_NAME": "demo-workflow",
        "CR_JOB_NAME": "themes-job",
        "CR_JOB_REGION": "europe-west2",
    }
    env.pop(missing_key)

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    for key in {
        "PROJECT_ID",
        "WORKFLOW_REGION",
        "WORKFLOW_NAME",
        "CR_JOB_NAME",
        "CR_JOB_REGION",
    } - env.keys():
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(WorkflowConfigError, match="Missing required workflow configuration"):
        get_workflow_config()


def test_trigger_workflow_creates_execution_with_expected_payload(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """Ensure workflow execution is created with the expected parent and payload."""

    dummy_client = DummyExecutionsClient()

    monkeypatch.setattr(
        "theme_analysis_ui.utils.workflow_utils.ExecutionsClient",
        lambda: dummy_client,
    )
    monkeypatch.setattr(
        "theme_analysis_ui.utils.workflow_utils.Execution",
        DummyExecution,
    )

    result = trigger_workflow(
        project_id="demo-project",
        region="europe-west2",
        workflow_name="demo-workflow",
        staging_bucket="demo-staging-bucket",
        csv_object="uploads/session-123/responses.csv",
        metadata_object="uploads/session-123/metadata.yaml",
        question="Why did you rate your GP practice experience as poor?",
        output_prefix="outputs/session-123",
        job_name="themes-job",
        job_region="europe-west2",
    )

    assert (
        result
        == "projects/demo-project/locations/europe-west2/workflows/demo-workflow/executions/123"
    )  # nosec B101
    assert len(dummy_client.calls) == 1  # nosec B101

    parent, execution = dummy_client.calls[0]
    assert (
        parent == "projects/demo-project/locations/europe-west2/workflows/demo-workflow"
    )  # nosec B101

    payload = json.loads(execution.argument)
    assert payload == {  # nosec B101
        "staging_bucket": "demo-staging-bucket",
        "csv_file": "responses.csv",
        "csv_object": "uploads/session-123/responses.csv",
        "metadata_object": "uploads/session-123/metadata.yaml",
        "question": "Why did you rate your GP practice experience as poor?",
        "output_prefix": "outputs/session-123",
        "output_bucket": "survey-assist-sandbox-themes-output",
        "job_name": "themes-job",
        "job_region": "europe-west2",
    }

    captured = capsys.readouterr()
    assert "Triggering workflow with payload:" in captured.out  # nosec B101


def test_trigger_workflow_uses_basename_for_csv_file(monkeypatch: MonkeyPatch) -> None:
    """Ensure only the basename of the CSV object is sent as csv_file."""

    dummy_client = DummyExecutionsClient()

    monkeypatch.setattr(
        "theme_analysis_ui.utils.workflow_utils.ExecutionsClient",
        lambda: dummy_client,
    )
    monkeypatch.setattr(
        "theme_analysis_ui.utils.workflow_utils.Execution",
        DummyExecution,
    )

    trigger_workflow(
        project_id="demo-project",
        region="europe-west2",
        workflow_name="demo-workflow",
        staging_bucket="demo-staging-bucket",
        csv_object="nested/path/to/input-file.csv",
        metadata_object="nested/path/to/metadata.yaml",
        question="What could be improved?",
        output_prefix="outputs/run-456",
        job_name="themes-job",
        job_region="europe-west2",
    )

    _, execution = dummy_client.calls[0]
    payload = json.loads(execution.argument)

    assert payload["csv_file"] == "input-file.csv"  # nosec B101
    assert payload["csv_object"] == "nested/path/to/input-file.csv"  # nosec B101
