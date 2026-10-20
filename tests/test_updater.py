import hashlib
import io
import json
import subprocess
import sys
import zipfile

import pytest

from core import updater


def _release_payload(version="0.2.0"):
    archive_name = f"Nyx-{version}-windows-x64-portable.zip"
    archive = b"test archive"
    release = {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "html_url": "https://github.com/Kronos1027/nyx-agent/releases/tag/v" + version,
        "assets": [
            {
                "name": archive_name,
                "size": len(archive),
                "browser_download_url": "https://github.com/Kronos1027/nyx-agent/archive.zip",
            },
            {
                "name": archive_name + ".sha256",
                "browser_download_url": "https://github.com/Kronos1027/nyx-agent/archive.zip.sha256",
            },
        ],
    }
    return release, archive


def test_update_check_finds_new_stable_release(monkeypatch):
    payload, _ = _release_payload()
    monkeypatch.setattr(updater, "_read_url", lambda url, limit: json.dumps(payload).encode())

    release = updater.check_for_update()

    assert release is not None
    assert release.version == "0.2.0"
    assert release.archive_name == "Nyx-0.2.0-windows-x64-portable.zip"


def test_update_check_ignores_current_version(monkeypatch):
    payload, _ = _release_payload("0.1.0")
    monkeypatch.setattr(updater, "_read_url", lambda url, limit: json.dumps(payload).encode())

    assert updater.check_for_update() is None


def test_update_check_requires_both_release_assets(monkeypatch):
    payload, _ = _release_payload()
    payload["assets"] = payload["assets"][:1]
    monkeypatch.setattr(updater, "_read_url", lambda url, limit: json.dumps(payload).encode())

    with pytest.raises(ValueError, match="checksum"):
        updater.check_for_update()


def _make_zip(*entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def test_stage_update_streams_and_extracts_verified_payload(tmp_path, monkeypatch):
    local_app_data = tmp_path / "local"
    install = local_app_data / "Programs" / "Nyx"
    install.mkdir(parents=True)
    (install / "Nyx.exe").write_bytes(b"old")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install / "Nyx.exe"))
    archive_bytes = _make_zip(("Nyx.exe", b"new executable"), ("install.ps1", b"installer"))
    release = updater.UpdateRelease(
        version="0.2.0",
        page_url="https://github.com/Kronos1027/nyx-agent/releases/tag/v0.2.0",
        archive_url="https://github.com/Kronos1027/nyx-agent/nyx.zip",
        checksum_url="https://github.com/Kronos1027/nyx-agent/nyx.zip.sha256",
        archive_name="Nyx-0.2.0-windows-x64-portable.zip",
        archive_size=len(archive_bytes),
    )
    monkeypatch.setattr(
        updater,
        "_read_url",
        lambda url, limit: f"{hashlib.sha256(archive_bytes).hexdigest()}  {release.archive_name}\n".encode(),
    )

    def write_archive(url, destination, limit, *, timeout):
        destination.write_bytes(archive_bytes)
        return len(archive_bytes), hashlib.sha256(archive_bytes).hexdigest()

    monkeypatch.setattr(updater, "_download_file", write_archive)
    payload = updater.stage_update(release)

    assert payload == local_app_data / "Nyx" / "updates" / "0.2.0" / "payload"
    assert (payload / "Nyx.exe").read_bytes() == b"new executable"
    assert not (payload.parent / release.archive_name).exists()


def test_stage_update_rejects_bad_checksum_and_cleans_staging(tmp_path, monkeypatch):
    local_app_data = tmp_path / "local"
    install = local_app_data / "Programs" / "Nyx"
    install.mkdir(parents=True)
    (install / "Nyx.exe").touch()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install / "Nyx.exe"))
    release = updater.UpdateRelease(
        "0.2.0", "https://github.com/x", "https://github.com/x.zip",
        "https://github.com/x.sha256", "Nyx-0.2.0-windows-x64-portable.zip", 1,
    )
    monkeypatch.setattr(updater, "_read_url", lambda url, limit: ("0" * 64 + "  " + release.archive_name).encode())
    monkeypatch.setattr(updater, "_download_file", lambda url, dest, limit, *, timeout: (1, "f" * 64))

    with pytest.raises(ValueError, match="SHA256"):
        updater.stage_update(release)
    assert not (local_app_data / "Nyx" / "updates" / "0.2.0").exists()


def test_generated_update_helper_parses_and_has_rollback(tmp_path, monkeypatch):
    local_app_data = tmp_path / "local"
    install = local_app_data / "Programs" / "Nyx"
    install.mkdir(parents=True)
    (install / "Nyx.exe").write_bytes(b"old")
    payload = local_app_data / "Nyx" / "updates" / "0.2.0" / "payload"
    payload.mkdir(parents=True)
    (payload / "Nyx.exe").write_bytes(b"new")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install / "Nyx.exe"))
    calls = []
    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: calls.append(args))

    updater.launch_staged_update(payload, 1234, "0.2.0")

    helper = payload.parent / "apply-update.ps1"
    script = helper.read_text(encoding="utf-8")
    assert "Wait-Process -Id $WaitPid" in script
    assert "Move-Item -LiteralPath $backup -Destination $install" in script
    assert "Autoteste da versão nova falhou." in script
    assert calls[0][0:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    escaped = str(helper).replace("'", "''")
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    process = real_popen(
        ["powershell.exe", "-NoProfile", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, stderr


@pytest.mark.parametrize("archive", [
    _make_zip(("../outside.txt", b"bad"), ("Nyx.exe", b"x")),
    _make_zip(("Nyx.exe:alternate", b"bad"), ("Nyx.exe", b"x")),
    _make_zip(("readme.txt", b"no executable")),
])
def test_extract_verified_payload_rejects_traversal_and_requires_exe(tmp_path, archive):
    archive_path = tmp_path / "payload.zip"
    archive_path.write_bytes(archive)
    with pytest.raises(ValueError):
        updater._extract_verified(archive_path, tmp_path / "out")
