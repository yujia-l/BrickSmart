from fastapi.testclient import TestClient

from bricksmart.app import app

client = TestClient(app)


def test_default_inventory_is_loaded_from_profile():
    """Test that default inventory is loaded from profile."""
    response = client.get("/api/inventory/default")
    assert response.status_code == 200
    payload = response.json()
    assert payload["blocks"]["standard_2x2x2"] == 16
    assert payload["blocks"]["bucket_arms"] == 1


def test_sample_plan_endpoint_passes():
    """Test that sample plan endpoint passes."""
    inventory = client.get("/api/inventory/default").json()
    problem = client.get("/api/problem/sample").json()
    response = client.post(
        "/api/plan",
        json={
            "inventory_mode": inventory["inventory_mode"],
            "inventory_id": inventory["inventory_id"],
            "quantities": inventory["blocks"],
            "scarcity_weight": problem["scarcity_weight"],
            "fail_on_required_group": problem["fail_on_required_group"],
            "groups": problem["groups"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PASS"
    assert payload["inventory_validation"]["status"] == "PASS"


def test_obj_endpoint_uses_csv_catalog():
    """Test that obj endpoint uses csv catalog."""
    response = client.post("/api/obj/plan", json={"model_uri": "model://bird-base"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"PASS", "FAIL_GEOMETRY_VALIDATION"}
    assert payload["catalog"]["source_path"].endswith("block_definitions.csv")
    assert payload["catalog"]["sources_read"] == ["block_definitions.csv"]
