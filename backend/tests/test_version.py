from importlib.metadata import version

from fastapi.testclient import TestClient

from app.version import APP_VERSION


def test_version_constant_matches_installed_metadata():
    assert APP_VERSION == "0.1.0"
    assert version("ai-act-trainer") == APP_VERSION


def test_version_endpoint_reports_app_course_and_law(client: TestClient):
    body = client.get("/api/version").json()
    assert body == {
        "app": "0.1.0",
        "course": "0.1.0",
        "law": {
            "celex": "02024R1689-20260727",
            "consolidated": "2026-07-27",
            "amended_by": ["32026R1744"],
        },
        "locales": ["de"],
        "reference_locale": "de",
        "acts": [
            {
                "id": "ai_act",
                "short_name": "KI-VO",
                "version": "02024R1689-20260727",
                "articles": 119,
            },
            {"id": "kimig", "short_name": "KI-MIG", "version": "20260729215513", "articles": 20},
            {"id": "bdsg", "short_name": "BDSG", "version": "20260713215512", "articles": 86},
            {
                "id": "betrvg",
                "short_name": "BetrVG",
                "version": "20260713215501",
                "articles": 145,
            },
            {
                "id": "geschgehg",
                "short_name": "GeschGehG",
                "version": "20210128212006",
                "articles": 23,
            },
            {
                "id": "gdpr",
                "short_name": "DSGVO",
                "version": "02016R0679-20160504",
                "articles": 99,
            },
            {
                "id": "qa",
                "short_name": "Q&A der Kommission",
                "version": "2026-09-15",
                "articles": 37,
            },
        ],
    }


def test_version_endpoint_law_tracks_the_corpus_act(client: TestClient):
    library = client.app.state.library
    act = library.acts["ai_act"].model_copy(update={"version": "02024R1689-20260827"})
    client.app.state.library = library.model_copy(update={"acts": {**library.acts, "ai_act": act}})
    body = client.get("/api/version").json()
    assert body["law"] == {
        "celex": "02024R1689-20260827",
        "consolidated": "2026-08-27",
        "amended_by": ["32026R1744"],
    }
    assert body["acts"][0]["version"] == "02024R1689-20260827"
