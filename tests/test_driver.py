from __future__ import annotations

from replayer.driver import PlaywrightCliDriver


def test_driver_todomvc_sequence() -> None:
    session_name = "replayer-test"
    with PlaywrightCliDriver(session_name) as driver:
        driver.open("https://demo.playwright.dev/todomvc/")
        initial_snapshot = driver.snapshot()

        assert any(node.role == "textbox" for node in initial_snapshot)

        textbox = next(node for node in initial_snapshot if node.role == "textbox")
        driver.fill(textbox.ref, "Buy groceries", submit=True)

        find_result = driver.find("Buy groceries")
        assert find_result.match_count == 1

        updated_snapshot = driver.snapshot()
        assert any(node.name == "Buy groceries" for node in updated_snapshot)

    assert PlaywrightCliDriver.list_sessions() == []
