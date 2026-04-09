from __future__ import annotations

import json
import os

from google.cloud.workflows.executions_v1 import ExecutionsClient
from google.cloud.workflows.executions_v1.types import Execution


class WorkflowConfigError(RuntimeError):
    """Raised when required workflow configuration is missing."""


def get_workflow_config() -> tuple[str, str, str, str, str]:
    """Load workflow configuration from environment variables.

    Returns:
        Tuple of (project_id, region, workflow_name, cr_job_name, cr_job_region).

    Raises:
        WorkflowConfigError: If any required variable is missing.
    """
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("WORKFLOW_REGION")
    workflow_name = os.getenv("WORKFLOW_NAME")
    cr_job_name = os.getenv("CR_JOB_NAME")
    cr_job_region = os.getenv("CR_JOB_REGION")

    if not project_id or not region or not workflow_name or not cr_job_name or not cr_job_region:
        raise WorkflowConfigError(
            "Missing required workflow configuration: "
            "PROJECT_ID, WORKFLOW_REGION, WORKFLOW_NAME, CR_JOB_NAME, CR_JOB_REGION are mandatory.",
        )

    return project_id, region, workflow_name, cr_job_name, cr_job_region


def trigger_workflow(
    *,
    project_id: str,
    region: str,
    workflow_name: str,
    staging_bucket: str,
    csv_object: str,
    metadata_object: str,
    question: str,
    output_prefix: str,
    job_name: str,
    job_region: str,
) -> str:
    """Start a workflow execution for a newly uploaded analysis request.

    Args:
        project_id: GCP project ID.
        region: Workflow region.
        workflow_name: Workflow name.
        staging_bucket: GCS bucket containing uploaded files.
        csv_object: GCS object path for the CSV.
        metadata_object: GCS object path for the metadata YAML.
        question: Analysis question to pass to downstream processing.
        output_prefix: GCS prefix for outputs.
        job_name: Cloud Run Job name.
        job_region: Region of the Cloud Run Job.

    Returns:
        The created workflow execution name.
    """
    client = ExecutionsClient()
    parent = f"projects/{project_id}/locations/{region}/workflows/{workflow_name}"

    csv_filename = os.path.basename(csv_object)
    payload = {
        "staging_bucket": staging_bucket,
        "csv_file": csv_filename,
        "csv_object": csv_object,
        "metadata_object": metadata_object,
        "question": question,
        "output_prefix": output_prefix,
        "output_bucket": "survey-assist-sandbox-themes-output",
        "job_name": job_name,
        "job_region": job_region,
    }

    # log the payload for debugging purposes
    print(f"Triggering workflow with payload: {json.dumps(payload)}")

    execution = Execution(argument=json.dumps(payload))
    response = client.create_execution(parent=parent, execution=execution)
    return response.name
