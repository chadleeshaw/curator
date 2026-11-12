"""Pull requests build the image and do not publish it."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def _step(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


def test_pull_requests_build_without_pushing_and_check_the_runtime_user():
    jobs = _workflow()["jobs"]
    verify = jobs["docker-image"]
    publish = jobs["build-and-push"]

    assert verify["if"] == "github.event_name == 'pull_request'"
    assert publish["if"] == "github.event_name == 'push'"

    image = _step(verify, "Build image")
    assert image["with"]["push"] is False
    assert image["with"]["load"] is True

    run = _step(verify, "Run as a non-root user")["run"]
    assert "PUID=1000" in run
    assert "PGID=1000" in run
    assert "/api/health" in run
    assert '!= "0"' in run

    logs = _step(verify, "Dump container logs")
    assert logs["if"] == "failure()"
    assert "docker logs" in logs["run"]


def test_release_images_include_arm64():
    publish = _workflow()["jobs"]["build-and-push"]
    build = _step(publish, "Build and push Docker image")
    platforms = build["with"]["platforms"]
    assert "linux/amd64" in platforms
    assert "linux/arm64" in platforms
    assert build["with"]["push"] is True
