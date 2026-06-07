from pathlib import Path
from unittest.mock import patch, MagicMock

from cae.docker_run import in_container, exec_in


def test_in_container_returns_true_when_dockerenv_exists(monkeypatch, tmp_path):
    fake_rootfs = tmp_path
    (fake_rootfs / ".dockerenv").touch()
    monkeypatch.setattr("pathlib.Path.root", lambda: fake_rootfs)
    assert in_container() is True


def test_in_container_returns_false_when_no_dockerenv(monkeypatch, tmp_path):
    fake_rootfs = tmp_path
    monkeypatch.setattr("pathlib.Path.root", lambda: fake_rootfs)
    assert in_container() is False


def test_exec_in_builds_docker_exec_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        exec_in("my-image", ["ls", "/work"], workdir=Path("/tmp"), timeout=60, env_file=None)
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0:2] == ["docker", "run"]
        assert "my-image" in cmd
        assert "ls" in cmd
        assert "/work" in cmd


def test_exec_in_passes_env_file_when_provided():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        exec_in("my-image", ["ls"], workdir=Path("/tmp"), timeout=60, env_file=Path("/tmp/env"))
        cmd = mock_run.call_args[0][0]
        assert "--env-file" in cmd
        assert "/tmp/env" in cmd
