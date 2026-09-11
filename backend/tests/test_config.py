"""Settings parsing, including the env quirks that bit us during scaffolding."""

from app.config import Settings


def test_blank_budget_env_vars_are_treated_as_unset() -> None:
    # `.env` files carry `ARM_BUDGET_CPU_CORES=` for "not configured"; pydantic
    # would otherwise fail to parse the empty string as a float.
    settings = Settings(budget_cpu_cores="", budget_memory_gi="")  # type: ignore[arg-type]
    assert settings.budget_cpu_cores is None
    assert settings.budget_memory_gi is None


def test_csv_settings_split_into_lists() -> None:
    settings = Settings(guarded_names="a, b ,, c")
    assert settings.guarded_name_list == ["a", "b", "c"]


def test_read_only_defaults_closed() -> None:
    # The master kill switch must default to closed; the API relies on it.
    settings = Settings()
    assert settings.read_only is True
    assert settings.allow_guarded_actions is False
    assert settings.allow_database_scaling is False
