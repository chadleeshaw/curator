"""The container entrypoint must boot from the config template that ships in the image."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker-entrypoint.sh"


def _env(tmp_path, config_text="search_providers: []\n"):
    template = tmp_path / "config.template.yaml"
    template.write_text(config_text)
    dest = tmp_path / "config" / "config.yaml"
    env = os.environ.copy()
    env["CONFIG_TEMPLATE"] = str(template)
    env["CONFIG_FILE"] = str(dest)
    env.setdefault("PUID", "1000")
    env.setdefault("PGID", "1000")
    return env, dest


def _run(tmp_path, *args, config_text="search_providers: []\n"):
    env, dest = _env(tmp_path, config_text)
    result = subprocess.run(
        ["bash", "-c", f'source "{ENTRYPOINT}"; ensure_config'],
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


def test_root_ids_are_refused(tmp_path):
    env, dest = _env(tmp_path)
    env["PUID"] = "0"
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "true"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "root" in result.stderr.lower()
    assert not dest.exists()

    env["PUID"] = "1000"
    env["PGID"] = "0"
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "true"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not dest.exists()


def test_privileges_drop_with_setpriv_and_chown_only_data_dirs():
    text = ENTRYPOINT.read_text()
    assert "setpriv --reuid" in text
    assert 'chown -R "$PUID:$PGID" "$dir"' in text
    assert "ownership_is_wrong" in text
    assert "/app/local/config" in text
    assert "/app/local/data" in text
    assert "chown -R /app\n" not in text
    assert "chown -R /app " not in text
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "--start-period=60s" in dockerfile


def test_chown_is_skipped_when_the_tree_already_matches(tmp_path):
    data = tmp_path / "downloads"
    data.mkdir()
    (data / "issue.pdf").write_text("pdf")
    log = tmp_path / "chown.log"
    env = os.environ.copy()
    env["PUID"] = str(os.getuid())
    env["PGID"] = str(os.getgid())
    env["DATA_DIRS"] = str(data)
    script = f"""
    source "{ENTRYPOINT}"
    chown() {{ printf '%s\\n' "$*" >> "{log}"; }}
    prepare_runtime_user
    """
    result = subprocess.run(["bash", "-c", script], cwd=ROOT, env=env, check=False, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert not log.exists()


def test_chown_runs_when_ownership_is_wrong(tmp_path):
    data = tmp_path / "downloads"
    data.mkdir()
    (data / "issue.pdf").write_text("pdf")
    log = tmp_path / "chown.log"
    other_id = "65534" if os.getuid() != 65534 else "65533"
    env = os.environ.copy()
    env["PUID"] = other_id
    env["PGID"] = other_id
    env["DATA_DIRS"] = str(data)
    script = f"""
    source "{ENTRYPOINT}"
    groupadd() {{ return 0; }}
    useradd() {{ return 0; }}
    chown() {{ printf '%s\\n' "$*" >> "{log}"; }}
    prepare_runtime_user
    """
    result = subprocess.run(["bash", "-c", script], cwd=ROOT, env=env, check=False, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert log.read_text().strip() == f"-R {other_id}:{other_id} {data}"
