"""会话信息 JSON 的写入与不覆盖规则。"""

import json
from uuid import uuid4

import pytest

from src.session_metadata import save_session_metadata


def test_saves_only_known_runtime_facts(tmp_path):
    run_id = uuid4().hex
    path = tmp_path / "session.json"
    assert save_session_metadata(run_id, 0, "DSHOW", 640, 480, path) == path
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == run_id
    assert data["source"] == "camera_test_runtime"
    assert data["camera_index_configured"] == 0
    assert data["backend_reported_by_opencv"] == "DSHOW"
    assert (data["frame_width_px"], data["frame_height_px"]) == (640, 480)
    assert "auto_exposure" not in data
    assert "lighting" not in data
    assert data["metadata_recorded_at"]


def test_unknown_backend_is_explicit_null(tmp_path):
    path = tmp_path / "session.json"
    save_session_metadata(uuid4().hex, 0, None, 640, 480, path)
    assert json.loads(path.read_text(encoding="utf-8"))["backend_reported_by_opencv"] is None


def test_existing_session_is_not_overwritten(tmp_path):
    path = tmp_path / "session.json"
    run_id = uuid4().hex
    save_session_metadata(run_id, 0, "DSHOW", 640, 480, path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_session_metadata(run_id, 0, "MSMF", 800, 600, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("run_id,index,backend,width,height", [
    ("../outside", 0, "DSHOW", 640, 480),
    (uuid4().hex, -1, "DSHOW", 640, 480),
    (uuid4().hex, 0, "", 640, 480),
    (uuid4().hex, 0, "DSHOW", 0, 480),
])
def test_invalid_metadata_does_not_create_file(tmp_path, run_id, index, backend, width, height):
    path = tmp_path / "session.json"
    with pytest.raises(ValueError):
        save_session_metadata(run_id, index, backend, width, height, path)
    assert not path.exists()
