import pytest

from bricksmart.exceptions import InventoryUnavailableError
from bricksmart.inventory import InventoryLedger, compile_effective_inventory
from bricksmart.inventory.models import InventoryMode, InventoryProfile


def finite_ledger(**quantities):
    profile = InventoryProfile("test", "test", InventoryMode.FINITE, quantities)
    return InventoryLedger(compile_effective_inventory(profile))


def test_atomic_reservation_does_not_partially_consume_stock():
    ledger = finite_ledger(big_wheel=1, angle_joint=2)
    with pytest.raises(InventoryUnavailableError):
        ledger.reserve({"big_wheel": 2, "angle_joint": 1}, reason="wheel_pair")
    assert ledger.remaining("big_wheel") == 1
    assert ledger.remaining("angle_joint") == 2
    assert ledger.committed_counts == {}


def test_release_restores_reserved_stock():
    ledger = finite_ledger(big_wheel=2)
    reservation = ledger.reserve({"big_wheel": 2}, reason="pair")
    assert ledger.remaining("big_wheel") == 0
    ledger.release(reservation)
    assert ledger.remaining("big_wheel") == 2


def test_commit_moves_reserved_to_committed():
    ledger = finite_ledger(rotation_block=2)
    reservation = ledger.reserve({"rotation_block": 1}, reason="feature")
    ledger.commit(reservation)
    assert ledger.reserved("rotation_block") == 0
    assert ledger.committed("rotation_block") == 1
    assert ledger.remaining("rotation_block") == 1
