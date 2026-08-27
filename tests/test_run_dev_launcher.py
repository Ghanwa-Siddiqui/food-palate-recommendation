import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_dev.ps1"
REQUIRED = (
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SESSION_SECRET",
)


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in REQUIRED:
        environment.pop(name, None)
    return environment


def _run(env_file: Path, environment: dict[str, str] | None = None):
    executable = shutil.which("pwsh")
    assert executable, "PowerShell 7 is required to test the development launcher"
    return subprocess.run(
        [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-EnvFile",
            str(env_file),
            "-ValidateOnly",
        ],
        cwd=ROOT,
        env=environment or _clean_environment(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_validation_only_parses_supported_dotenv_values_without_starting(tmp_path):
    marker = ROOT / ".dev-logs"
    existed_before = marker.exists()
    env_file = tmp_path / "launcher.env"
    env_file.write_text(
        "\n# comment\n"
        "DATABASE_URL='postgresql://user:p=a=s=s@localhost/chaska' # inline comment\n"
        'SUPABASE_URL="https://example.invalid/#fragment"\n'
        "SUPABASE_PUBLISHABLE_KEY=public=value=with=equals # comment\n"
        'SESSION_SECRET="0123456789abcdef0123456789abcdef" # comment\n',
        encoding="utf-8",
    )

    result = _run(env_file)

    assert result.returncode == 0
    assert result.stdout.strip() == "Development launcher configuration is valid."
    assert "0123456789abcdef" not in result.stdout + result.stderr
    if not existed_before:
        assert not marker.exists()


def test_process_environment_has_priority_over_dotenv(tmp_path):
    env_file = tmp_path / "launcher.env"
    env_file.write_text(
        "DATABASE_URL=\nSUPABASE_URL=\nSUPABASE_PUBLISHABLE_KEY=\nSESSION_SECRET=short\n",
        encoding="utf-8",
    )
    environment = _clean_environment()
    environment.update(
        DATABASE_URL="postgresql://process-value",
        SUPABASE_URL="https://process.invalid",
        SUPABASE_PUBLISHABLE_KEY="process-public-key",
        SESSION_SECRET="p" * 32,
    )

    result = _run(env_file, environment)

    assert result.returncode == 0
    assert "process-public-key" not in result.stdout + result.stderr


@pytest.mark.parametrize("missing", REQUIRED)
def test_validation_only_rejects_missing_required_value(tmp_path, missing):
    values = {
        "DATABASE_URL": "postgresql://localhost/chaska",
        "SUPABASE_URL": "https://example.invalid",
        "SUPABASE_PUBLISHABLE_KEY": "public-key",
        "SESSION_SECRET": "s" * 32,
    }
    values[missing] = ""
    env_file = tmp_path / "launcher.env"
    env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )

    result = _run(env_file)

    assert result.returncode != 0
    assert missing in result.stderr
    if values["SESSION_SECRET"]:
        assert values["SESSION_SECRET"] not in result.stdout + result.stderr


def test_validation_only_rejects_short_session_secret(tmp_path):
    env_file = tmp_path / "launcher.env"
    env_file.write_text(
        "DATABASE_URL=postgresql://localhost/chaska\n"
        "SUPABASE_URL=https://example.invalid\n"
        "SUPABASE_PUBLISHABLE_KEY=public-key\n"
        "SESSION_SECRET=too-short\n",
        encoding="utf-8",
    )

    result = _run(env_file)

    assert result.returncode != 0
    assert "32 characters" in result.stderr
    assert "too-short" not in result.stdout + result.stderr


def test_invalid_dotenv_line_is_rejected_without_echoing_it(tmp_path):
    env_file = tmp_path / "launcher.env"
    secret_line = "not valid and must not be echoed"
    env_file.write_text(secret_line + "\n", encoding="utf-8")

    result = _run(env_file)

    assert result.returncode != 0
    assert "Invalid environment entry" in result.stderr
    assert secret_line not in result.stdout + result.stderr
