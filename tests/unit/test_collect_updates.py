from juliabot.collect_updates import CommitInfo, UpdateCollector


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_get_all_commits_uses_github_when_configured(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        if params["page"] == 1:
            return _FakeResponse(
                [
                    {
                        "sha": "abcdef123456",
                        "commit": {
                            "message": "feat: add github source\n\nmore details",
                            "author": {"name": "Julia", "date": "2026-03-07T12:00:00Z"},
                        },
                    }
                ]
            )
        return _FakeResponse([])

    monkeypatch.setattr("juliabot.collect_updates.GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr("juliabot.collect_updates.requests.get", fake_get)
    monkeypatch.setattr(
        UpdateCollector, "_fetch_commits_from_git", lambda limit=None: []
    )

    commits = UpdateCollector.get_all_commits()

    assert len(commits) == 1
    assert commits[0].hash == "abcdef1"
    assert commits[0].message == "feat: add github source"
    assert commits[0].author == "Julia"
    assert commits[0].date == "2026-03-07"
    assert calls[0][0] == "https://api.github.com/repos/owner/repo/commits"


def test_get_all_commits_falls_back_to_git_when_github_fails(monkeypatch):
    def fake_get(url, params, timeout):
        raise RuntimeError("network down")

    def fake_git(limit=None):
        return [CommitInfo("1234567", "fix: fallback", "Dev", "2026-03-01")]

    monkeypatch.setattr("juliabot.collect_updates.GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr("juliabot.collect_updates.requests.get", fake_get)
    monkeypatch.setattr(UpdateCollector, "_fetch_commits_from_git", fake_git)

    commits = UpdateCollector.get_all_commits()

    assert len(commits) == 1
    assert commits[0].message == "fix: fallback"


def test_get_commits_since_hash_filters_in_memory(monkeypatch):
    commits = [
        CommitInfo("aaaa111", "feat: a", "A", "2026-03-08"),
        CommitInfo("bbbb222", "fix: b", "B", "2026-03-07"),
        CommitInfo("cccc333", "chore: c", "C", "2026-03-06"),
    ]
    monkeypatch.setattr(UpdateCollector, "get_all_commits", lambda limit=None: commits)

    filtered = UpdateCollector.get_commits_since_hash("bbbb222")

    assert [c.hash for c in filtered] == ["aaaa111"]


def test_get_commits_since_date_filters_in_memory(monkeypatch):
    commits = [
        CommitInfo("aaaa111", "feat: a", "A", "2026-03-08"),
        CommitInfo("bbbb222", "fix: b", "B", "2 days ago"),
        CommitInfo("cccc333", "chore: c", "C", "2026-03-06"),
    ]
    monkeypatch.setattr(UpdateCollector, "get_all_commits", lambda limit=None: commits)

    filtered = UpdateCollector.get_commits_since_date("2026-03-07")

    assert [c.hash for c in filtered] == ["aaaa111"]


def test_get_last_n_commits_uses_single_source(monkeypatch):
    seen = {}

    def fake_all(limit=None):
        seen["limit"] = limit
        return [CommitInfo("aaaa111", "feat: a", "A", "2026-03-08")]

    monkeypatch.setattr(UpdateCollector, "get_all_commits", fake_all)

    commits = UpdateCollector.get_last_n_commits(1)

    assert seen["limit"] == 1
    assert len(commits) == 1
