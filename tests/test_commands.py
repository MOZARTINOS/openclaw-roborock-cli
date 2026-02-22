from roborock_cli.commands import format_clean_summary, format_consumables, format_status


def test_format_status_happy_path() -> None:
    payload = {
        "state": 8,
        "battery": 92,
        "fan_power": 104,
        "clean_time": 3090,
        "clean_area": 37100000,
        "water_box_status": 1,
        "water_box_carriage_status": 1,
    }

    result = format_status(payload)

    assert "State:      Charging" in result
    assert "Battery:    92%" in result
    assert "Fan speed:  Max" in result
    assert "Clean area: 37.1 m^2" in result
    assert "Water tank: Installed" in result


def test_format_consumables_warns_when_near_end_of_life() -> None:
    payload = {
        "main_brush_work_time": 1070000,
        "side_brush_work_time": 200000,
        "filter_work_time": 120000,
        "sensor_dirty_time": 50000,
    }

    result = format_consumables(payload)

    assert "Consumables:" in result
    assert "Main brush" in result
    assert "Maintenance alerts:" in result
    assert "Main brush is near replacement" in result


def test_format_clean_summary() -> None:
    payload = {
        "clean_count": 55,
        "clean_time": 14400,
        "clean_area": 210000000,
    }

    result = format_clean_summary(payload)

    assert "Sessions:   55" in result
    assert "Total time: 4h 0m" in result
    assert "Total area: 210.0 m^2" in result
