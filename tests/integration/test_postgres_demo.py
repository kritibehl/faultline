from pathlib import Path
import json

def test_replay_files_exist():
    replay_dir = Path("replays")
    files = list(replay_dir.glob("*.json"))
    assert len(files) >= 4

    for p in files:
        data = json.loads(p.read_text())
        assert "failure_case" in data
        assert "expected_behavior" in data
