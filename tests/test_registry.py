from unipro.config import Settings
from unipro.providers.registry import ProviderRegistry


def test_live_registry_uses_real_providers_only():
    settings = Settings(
        demo_mode=False,
        enable_alibaba=True,
        enable_mrbilit=True,
        enable_safar724=True,
    )
    registry = ProviderRegistry.from_settings(settings)
    assert {p.provider_id for p in registry.providers} == {
        "alibaba",
        "mrbilit",
        "safar724",
        "snapptrip",
        "flytoday",
    }


def test_demo_registry_does_not_mix_live_inventory():
    settings = Settings(demo_mode=True)
    registry = ProviderRegistry.from_settings(settings)
    assert all(p.provider_id.startswith("demo_") for p in registry.providers)


def test_raja_requires_explicit_credentials():
    settings = Settings(
        demo_mode=False,
        enable_raja=True,
        raja_api_key="",
        raja_query_password="",
    )
    registry = ProviderRegistry.from_settings(settings)
    assert "raja" not in {p.provider_id for p in registry.providers}


def test_raja_is_registered_with_credentials():
    settings = Settings(
        demo_mode=False,
        enable_raja=True,
        raja_api_key="authorized-key",
        raja_query_password="authorized-password",
    )
    registry = ProviderRegistry.from_settings(settings)
    assert "raja" in {p.provider_id for p in registry.providers}
