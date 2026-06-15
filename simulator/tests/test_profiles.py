from app.main import CHANNEL_PROFILES


def test_profiles_cover_required_channels():
    assert {"whatsapp", "sms", "email", "rcs"}.issubset(CHANNEL_PROFILES)
    assert all(0 <= profile["failure"] < 1 for profile in CHANNEL_PROFILES.values())
