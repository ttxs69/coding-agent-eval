import subprocess
import sys


def test_pae_runs_and_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "pae", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "pae" in result.stdout.lower() or "usage" in result.stdout.lower()
