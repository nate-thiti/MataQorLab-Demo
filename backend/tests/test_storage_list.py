from app.services.storage_list import list_business_files


class FakeBucket:
    def __init__(self, rows):
        self.rows = rows
        self.path = None
        self.options = None

    def list(self, path, options):
        self.path = path
        self.options = options
        return self.rows


class FakeStorage:
    def __init__(self, bucket):
        self.bucket = bucket
        self.bucket_name = None

    def from_(self, bucket_name):
        self.bucket_name = bucket_name
        return self.bucket


class FakeClient:
    def __init__(self, rows):
        self.bucket = FakeBucket(rows)
        self.storage = FakeStorage(self.bucket)


def test_file_inventory_returns_stable_page_and_next_offset():
    client = FakeClient([
        {"name": "c.csv"},
        {"name": "b.csv"},
        {"name": "a.csv"},
    ])

    result = list_business_files(
        "user-1",
        limit=2,
        offset=20,
        search="sales",
        client=client,
    )

    assert [item["name"] for item in result["files"]] == ["c.csv", "b.csv"]
    assert result["has_more"] is True
    assert result["next_offset"] == 22
    assert client.storage.bucket_name == "business-data"
    assert client.bucket.path == "user-1"
    assert client.bucket.options["limit"] == 3
    assert client.bucket.options["offset"] == 20
    assert client.bucket.options["search"] == "sales"


def test_file_inventory_caps_page_size_and_marks_final_page():
    client = FakeClient([{"name": "only.csv"}])
    result = list_business_files("user-1", limit=500, client=client)

    assert result["limit"] == 100
    assert result["next_offset"] is None
    assert result["has_more"] is False
