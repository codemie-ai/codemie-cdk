import json
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))
import check_version as cv  # noqa: E402

SCRIPT = ROOT / "scripts" / "release" / "check_version.py"


def pypi(*versions):
    return lambda url: {"releases": {v: [] for v in versions}}


def npm(*versions):
    return lambda url: {"versions": {v: {} for v in versions}}


def test_equal_version_fails():
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "1.0.0", fetch=pypi("1.0.0"))


def test_higher_passes_and_returns_latest():
    assert cv.check("pypi", "x", "1.0.1", fetch=pypi("0.9", "1.0.0")) == "1.0.0"
    assert cv.check("npm", "x", "1.1.0", fetch=npm("1.0.0")) == "1.0.0"


def test_lower_fails():
    with pytest.raises(cv.VersionError):
        cv.check("npm", "x", "0.9.0", fetch=npm("1.0.0"))


def test_already_published_older_version_fails():
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "0.5", fetch=pypi("0.5", "1.0.0"))


def test_highest_in_list_is_used_not_insertion_order():
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "1.5.0", fetch=pypi("2.0.0", "1.0.0"))


def test_pep440_prerelease_ordering():
    assert cv.check("pypi", "x", "1.0.0", fetch=pypi("1.0.0rc1")) == "1.0.0rc1"
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "1.0.0rc1", fetch=pypi("1.0.0"))
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "1.0.0.dev1", fetch=pypi("1.0.0a1"))
    assert cv.check("pypi", "x", "1.0.0.post1", fetch=pypi("1.0.0")) == "1.0.0"
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "1.0", fetch=pypi("1.0.0"))


def test_semver_prerelease_ordering():
    assert cv.check("npm", "x", "1.0.0", fetch=npm("1.0.0-beta.1")) == "1.0.0-beta.1"
    with pytest.raises(cv.VersionError):
        cv.check("npm", "x", "1.0.0-beta.1", fetch=npm("1.0.0"))
    assert cv.check("npm", "x", "1.0.0-beta.11", fetch=npm("1.0.0-beta.2")) == "1.0.0-beta.2"
    assert cv.check("npm", "x", "1.0.0-rc.1", fetch=npm("1.0.0-beta.2")) == "1.0.0-beta.2"
    with pytest.raises(cv.VersionError):
        cv.check("npm", "x", "1.0.0-alpha", fetch=npm("1.0.0-alpha.1"))


def test_semver_build_metadata_ignored():
    with pytest.raises(cv.VersionError):
        cv.check("npm", "x", "1.0.0+b2", fetch=npm("1.0.0+b1"))


def test_not_on_registry_passes():
    assert cv.check("pypi", "x", "0.1.0", fetch=lambda url: None) == ""


def test_malformed_payload_fails_closed():
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", "1.0.0", fetch=lambda url: ["nope"])
    with pytest.raises(cv.VersionError):
        cv.check("npm", "x", "1.0.0", fetch=lambda url: {"versions": []})


def test_unparseable_own_version_fails():
    with pytest.raises(cv.VersionError):
        cv.check("npm", "x", "not-a-version", fetch=npm("1.0.0"))


def test_unknown_ecosystem_fails():
    with pytest.raises(cv.VersionError):
        cv.check("cargo", "x", "1.0.0", fetch=npm())


def test_urls():
    seen = []
    cv.check("pypi", "a-b", "1.0.0", fetch=lambda u: seen.append(u))
    cv.check("npm", "a-b", "1.0.0", fetch=lambda u: seen.append(u))
    assert seen == ["https://pypi.org/pypi/a-b/json", "https://registry.npmjs.org/a-b"]


@pytest.mark.parametrize(
    "eco,tag,base,expected",
    [
        ("pypi", "python-v0.1.665", "0.1.0", "0.1.665"),
        ("npm", "node-v0.1.665", "0.1.0", "0.1.665"),
        ("pypi", "python-v0.2.0", "0.2", "0.2.0"),
        ("npm", "node-v1.0.7", "1.0.0", "1.0.7"),
        ("pypi", "python-v0.1.665-rc0", "0.1.0", "0.1.665-rc0"),
        ("npm", "node-v0.1.665-rc0", "0.1.0", "0.1.665-rc0"),
        ("npm", "node-v0.1.665-rc1", "0.1.0", "0.1.665-rc1"),
        ("pypi", "python-v0.1.665-rc12", "0.1.0", "0.1.665-rc12"),
    ],
)
def test_tag_gives_the_version(eco, tag, base, expected):
    assert cv.version_from_tag(eco, tag, base) == expected


@pytest.mark.parametrize(
    "eco,tag",
    [
        ("pypi", "node-v0.1.665"),
        ("npm", "python-v0.1.665"),
        ("pypi", "v0.1.665"),
        ("pypi", "python-0.1.665"),
        ("pypi", "python-v0.1"),
        ("pypi", "python-v0.1.665rc1"),
        ("pypi", "python-v0.1.665-rc.0"),
        ("npm", "node-v0.1.665-rc.0"),
        ("npm", "node-v0.1.665-rc"),
        ("pypi", "python-v0.1.665-rc01"),
        ("npm", "node-v0.1.665-beta.1"),
        ("npm", "node-v0.1.665-beta0"),
        ("pypi", "python-v0.1.665-dev0"),
        ("pypi", "python-v0.1.665.1"),
        ("pypi", "python-v0.1.0665"),
        ("pypi", "python-v0.1.665 "),
        ("pypi", "python-v0.1.665\n"),
        ("npm", "node-v0.1.665\n"),
        ("pypi", "python-v0.1.\u0666"),
        ("pypi", "python-v0.1.6\u0666"),
        ("npm", "node-v\u0660.1.5"),
        ("pypi", "refs/tags/python-v0.1.665"),
        ("pypi", ""),
    ],
)
def test_bad_tag_fails(eco, tag):
    with pytest.raises(cv.VersionError):
        cv.version_from_tag(eco, tag, "0.1.0")


def test_tag_on_another_line_than_the_manifest_fails():
    with pytest.raises(cv.VersionError, match="line"):
        cv.version_from_tag("pypi", "python-v0.2.3", "0.1.0")
    with pytest.raises(cv.VersionError, match="line"):
        cv.version_from_tag("npm", "node-v1.0.0", "0.1.0")


@pytest.mark.parametrize("base", ["0", "0.1.5", "0.1.0-beta", "1.2.3.4", "v0.1", "", "x.y", "\u0660.1", "0.\u0661.0"])
def test_tag_rejects_bad_base(base):
    with pytest.raises(cv.VersionError, match="base"):
        cv.version_from_tag("pypi", "python-v0.1.665", base)


def test_tag_unknown_ecosystem_fails():
    with pytest.raises(cv.VersionError):
        cv.version_from_tag("cargo", "cargo-v0.1.1", "0.1.0")


def test_tag_version_must_still_beat_the_registry():
    ok = cv.version_from_tag("pypi", "python-v0.1.664", "0.1.0")
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", ok, fetch=pypi("0.1.664"))
    with pytest.raises(cv.VersionError):
        cv.check("pypi", "x", ok, fetch=pypi("0.1.700"))


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_cli_requires_tag_or_version():
    assert run_cli("--ecosystem", "npm", "--name", "x").returncode == 2


def test_cli_tag_needs_base():
    assert run_cli("--ecosystem", "npm", "--name", "x", "--tag", "node-v0.1.1").returncode == 2


def test_cli_base_alone_is_gone():
    assert run_cli("--ecosystem", "npm", "--name", "x", "--base", "0.1.0").returncode == 2


def test_cli_tag_prints_only_the_version(capsys):
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--tag", "python-v0.1.4", "--base", "0.1.0"]) == 0
    assert capsys.readouterr().out == "0.1.4\n"


def test_cli_tag_does_not_touch_the_network(monkeypatch):
    def boom(url):
        raise AssertionError("network used")

    monkeypatch.setattr(cv, "_fetch_json", boom)
    assert cv.main(["--ecosystem", "npm", "--name", "x", "--tag", "node-v0.1.4", "--base", "0.1.0"]) == 0


def test_cli_bad_tag_exits_1(capsys):
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--tag", "node-v0.1.4", "--base", "0.1.0"]) == 1
    assert "tag" in capsys.readouterr().err


def test_cli_network_error_exits_1(monkeypatch, capsys):
    def boom(url):
        raise URLError("down")

    monkeypatch.setattr(cv, "_fetch_json", boom)
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--version", "1.0.0"]) == 1
    assert "down" in capsys.readouterr().err


def test_cli_bad_json_exits_1(monkeypatch):
    def bad(url):
        return json.loads("{not json")

    monkeypatch.setattr(cv, "_fetch_json", bad)
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--version", "1.0.0"]) == 1


def test_cli_success_exits_0(monkeypatch):
    monkeypatch.setattr(cv, "_fetch_json", lambda url: None)
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--version", "1.0.0"]) == 0


def http_error(code):
    return cv.urllib.error.HTTPError("https://x", code, "msg", {}, None)


def test_real_fetch_404_means_not_published(monkeypatch):
    def raise_404(req, timeout):
        raise http_error(404)

    monkeypatch.setattr(cv.urllib.request, "urlopen", raise_404)
    assert cv._fetch_json("https://x") is None
    assert cv.main(["--ecosystem", "npm", "--name", "x", "--version", "1.0.0"]) == 0


def test_real_fetch_server_error_fails_closed(monkeypatch):
    def raise_500(req, timeout):
        raise http_error(500)

    monkeypatch.setattr(cv.urllib.request, "urlopen", raise_500)
    with pytest.raises(cv.urllib.error.HTTPError):
        cv._fetch_json("https://x")
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--version", "1.0.0"]) == 1


@pytest.mark.parametrize(
    "eco,fetch",
    [("pypi", pypi("1.0.0", "legacy-build")), ("npm", npm("1.0.0", "1.0")), ("npm", npm("garbage"))],
)
def test_unparseable_registry_version_fails_closed(eco, fetch):
    with pytest.raises(cv.VersionError, match="unparseable"):
        cv.check(eco, "x", "2.0.0", fetch=fetch)


def test_cli_unparseable_registry_version_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(cv, "_fetch_json", pypi("1.0.0", "legacy-build"))
    assert cv.main(["--ecosystem", "pypi", "--name", "x", "--version", "2.0.0"]) == 1
    assert "legacy-build" in capsys.readouterr().err
def test_scoped_npm_name_is_url_encoded():
    seen = []

    def fetch(url):
        seen.append(url)
        return {"versions": {"0.1.0": {}}}

    cv.check("npm", "@codemieai/cdk", "0.2.0", fetch=fetch)
    assert seen == ["https://registry.npmjs.org/@codemieai%2Fcdk"]


def test_unscoped_name_url_unchanged():
    seen = []
    cv.check("pypi", "codemie-sdk", "1.0.1", fetch=lambda u: seen.append(u) or {"releases": {}})
    assert seen == ["https://pypi.org/pypi/codemie-sdk/json"]


def test_custom_tag_prefix_for_cdk():
    assert cv.version_from_tag("npm", "cdk-v0.2.1", "0.2.0", prefix="cdk-v") == "0.2.1"
    with pytest.raises(cv.VersionError):
        cv.version_from_tag("npm", "node-v0.2.1", "0.2.0", prefix="cdk-v")
    with pytest.raises(cv.VersionError):
        cv.version_from_tag("npm", "cdk-v0.2.1", "0.2.0")  # default prefix unchanged
    with pytest.raises(cv.VersionError, match="line"):
        cv.version_from_tag("npm", "cdk-v0.3.0", "0.2.0", prefix="cdk-v")


def test_cli_tag_prefix(capsys):
    rc = cv.main(["--ecosystem", "npm", "--name", "@codemieai/cdk", "--tag", "cdk-v0.2.1", "--base", "0.2.0",
                  "--tag-prefix", "cdk-v"])
    assert rc == 0
    assert capsys.readouterr().out == "0.2.1\n"


def test_cli_tag_prefix_only_works_with_tag():
    assert run_cli("--ecosystem", "npm", "--name", "x", "--version", "1.0.0", "--tag-prefix", "cdk-v").returncode == 2


def test_cdk_release_candidate_tag_names_a_prerelease():
    assert cv.version_from_tag("npm", "cdk-v0.2.1-rc1", "0.2.0", prefix="cdk-v") == "0.2.1-rc1"
    for bad in ("cdk-v0.2.1-rc", "cdk-v0.2.1-beta1", "cdk-v0.2.1-rc01", "cdk-v0.2.1-rc1-x"):
        with pytest.raises(cv.VersionError):
            cv.version_from_tag("npm", bad, "0.2.0", prefix="cdk-v")


def test_check_version_accepts_mcp_prefix():
    assert cv.version_from_tag("pypi", "mcp-assistants-v0.2.1", "0.2.0", prefix="mcp-assistants-v") == "0.2.1"
    assert cv.version_from_tag("pypi", "mcp-workflows-v0.2.1-rc1", "0.2.0", prefix="mcp-workflows-v") == "0.2.1-rc1"


def test_check_version_rejects_other_package_prefix():
    for tag in ("mcp-workflows-v0.2.1", "mcp-datasources-v0.2.1", "python-v0.2.1", "mcp-assistants-v0.3.0"):
        with pytest.raises(cv.VersionError):
            cv.version_from_tag("pypi", tag, "0.2.0", prefix="mcp-assistants-v")

