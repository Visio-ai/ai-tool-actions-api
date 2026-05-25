from __future__ import annotations

from fastapi import FastAPI

from capabilities_solutions_api.main import telemetry
from capabilities_solutions_api.main.settings import Settings


def test_configure_telemetry_skips_when_endpoint_is_missing() -> None:
    app = FastAPI()

    telemetry.configure_telemetry(app, Settings())

    assert not hasattr(app.state, "otel_instrumented")


def test_configure_telemetry_uses_standard_otlp_env_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "tempo.monitoring:4317")

    assert telemetry.resolve_otlp_endpoint(Settings()) == "tempo.monitoring:4317"


def test_configure_telemetry_instruments_each_app_only_once(monkeypatch) -> None:
    app = FastAPI()
    calls = {"instrument_app": 0}

    monkeypatch.setattr(telemetry, "_configure_provider", lambda settings, endpoint: None)
    monkeypatch.setattr(
        telemetry.FastAPIInstrumentor,
        "instrument_app",
        lambda target_app: calls.__setitem__("instrument_app", calls["instrument_app"] + 1),
    )

    settings = Settings(otlp_endpoint="tempo.monitoring:4317")
    telemetry.configure_telemetry(app, settings)
    telemetry.configure_telemetry(app, settings)

    assert calls["instrument_app"] == 1
    assert app.state.otel_instrumented is True
