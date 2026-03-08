from merlin_auth import parse_api_key_collection, load_api_key_collection_from_file


def test_parse_api_key_collection_normalizes_and_deduplicates():
    keys = parse_api_key_collection(" alpha, beta\nalpha, ,gamma ")
    assert keys == ["alpha", "beta", "gamma"]


def test_load_api_key_collection_from_file(tmp_path):
    key_file = tmp_path / "keys.txt"
    key_file.write_text("k1\nk2,k3", encoding="utf-8")

    keys = load_api_key_collection_from_file(str(key_file))

    assert keys == ["k1", "k2", "k3"]
