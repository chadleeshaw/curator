"""The container entrypoint must boot from the config template that ships in the image."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker-entrypoint.sh"


def _run(tmp_path, *args, config_text="search_providers: []\n"):
    template = tmp_path / "config.template.yaml"
    template.write_text(config_text)
    dest = tmp_path / "config" / "config.yaml"
    env = os.environ.copy()
    env["CONFIG_TEMPLATE"] = str(template)
    env["CONFIG_FILE"] = str(dest)
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), *args],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, dest


def test_first_run_copies_the_template(tmp_path):
    result, dest = _run(tmp_path, "true")

    assert result.returncode == 0, result.stderr
    assert dest.read_text() == "search_providers: []\n"


def test_an_existing_config_is_left_alone(tmp_path):
    _, dest = _run(tmp_path, "true")
    dest.write_text("user: true\n")

    result, dest = _run(tmp_path, "true", config_text="replaced: true\n")

    assert result.returncode == 0, result.stderr
    assert dest.read_text() == "user: true\n"


def test_entrypoint_does_not_copy_the_missing_sample():
    text = ENTRYPOINT.read_text()
    assert "config.sample.yaml" not in text
    assert "config.template.yaml" in text
