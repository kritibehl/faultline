from home_automation_scenarios.run_home_automation_replay import (
    load_scenario,
    run_all,
    validate_accessory_offline_reconnect,
    validate_controller_accessory_partition,
    validate_duplicate_scene_command,
    validate_multi_device_scene_replay,
    validate_stale_controller_command,
)


def test_accessory_offline_reconnect_recovers_state():
    result = validate_accessory_offline_reconnect(
        load_scenario("accessory_offline_reconnect")
    )

    assert result["passed"] is True


def test_stale_controller_command_rejected():
    result = validate_stale_controller_command(
        load_scenario("stale_controller_command")
    )

    assert result["passed"] is True


def test_duplicate_scene_command_prevented():
    result = validate_duplicate_scene_command(
        load_scenario("duplicate_scene_command")
    )

    assert result["passed"] is True


def test_multi_device_scene_replay_validated():
    result = validate_multi_device_scene_replay(
        load_scenario("multi_device_scene_replay")
    )

    assert result["passed"] is True


def test_controller_accessory_partition_handled():
    result = validate_controller_accessory_partition(
        load_scenario("controller_accessory_partition")
    )

    assert result["passed"] is True


def test_home_automation_suite_passes_all_scenarios():
    result = run_all()

    assert result["passed"] == 5
    assert result["total"] == 5
    assert result["all_passed"] is True
