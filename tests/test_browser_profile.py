import pytest

from tools.browser_profile import BrowserProfile


def test_persistent_profile_is_exclusive_and_preserved(tmp_path):
    path = tmp_path / "owned"
    profile = BrowserProfile(path)
    (path / "session-test").write_text("keep")
    with pytest.raises(ValueError, match="uso"):
        BrowserProfile(path)
    profile.close()
    assert (path / "session-test").read_text() == "keep"
    reopened = BrowserProfile(path)
    reopened.close()


def test_existing_personal_directory_is_never_adopted(tmp_path):
    (tmp_path / "Cookies").write_text("private")
    with pytest.raises(ValueError, match="pessoal"):
        BrowserProfile(tmp_path)
    assert (tmp_path / "Cookies").read_text() == "private"
    assert not (tmp_path / ".nyx-profile").exists()


def test_temporary_profile_is_removed_on_close():
    profile = BrowserProfile()
    assert profile.path.exists()
    profile.close()
    assert not profile.path.exists()
