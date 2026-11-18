"""Block parameters are read from the program, classified by the shipped TechDoc table."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"
spec = importlib.util.spec_from_file_location("block_parameters", ROOT / "block_parameters.py")
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

U = "20fd118e-02ad-b7{:02x}-00ffcd7c89c3e057"
PROGRAM = f'''<C Type="Document"><C Type="Program">
  <C Type="AutoJalousie" U="20fd118e-02ad-b7da-ffffa13734b4be2f" Title="Beschattung Buero">
    <Co K="InputTrigger" U="{U.format(1)}"/>
    <Co K="TimeEnd" Def="75" U="{U.format(2)}"/>
    <Co K="TimeBlock" Def="0,5" U="{U.format(3)}"/>
    <Co K="Deadtime" U="{U.format(4)}"/>
    <Co K="TimeEndDown" Def="70" U="{U.format(5)}"><In Input="{U.format(9)}"/></Co>
    <IoData Visu="true" Pr="room-1"/>
  </C>
  <C Type="Greater" U="20fd118e-0299-0001-ffffa13734b4be2f">
    <Co K="Input2" Def="21.5" U="{U.format(6)}"/>
  </C>
  <C Type="NoSuchBlock" U="20fd118e-0299-0002-ffffa13734b4be2f"><Co K="TimeEnd" Def="1" U="{U.format(7)}"/></C>
</C></C>'''.encode()


def by_key(params):
    return {p["key"]: p for p in params}


def test_shipped_table_classifies_parameters_not_inputs():
    params = by_key(bp.enumerate_parameters(PROGRAM))
    # Inputs are no parameters; wired parameters have no fixed value.
    assert "InputTrigger" not in params and "TimeEndDown" not in params
    assert params["TimeEnd"]["value"] == 75.0 and params["TimeEnd"]["unit"] == "s"
    assert params["TimeEnd"]["label"] == "Opening duration"
    assert params["TimeBlock"]["value"] == 0.5  # decimal comma
    assert params["Deadtime"]["value"] == 0.0  # Config omits Def for 0
    assert params["TimeEnd"]["unique_id"] == U.format(2)
    assert params["TimeEnd"]["visu"] and params["TimeEnd"]["room"] == "room-1"
    assert params["TimeEnd"]["block_title"] == "Beschattung Buero"


def test_numbered_parameters_and_logic_blocks_start_hidden():
    params = by_key(bp.enumerate_parameters(PROGRAM))
    assert params["Input2"]["value"] == 21.5
    assert params["Input2"]["label"].endswith(" 2")
    assert params["Input2"]["visu"] is False
    assert all(p["block_type"] != "NoSuchBlock" for p in params.values())


def test_structure_uuids_are_not_duplicated_and_values_refresh():
    params = bp.enumerate_parameters(PROGRAM)
    loxconfig = {"controls": {"x": {"states": {"comfort": U.format(2)}}}}
    assert U.format(2) not in {p["unique_id"] for p in bp.without_structure_ids(params, loxconfig)}
    changed = PROGRAM.replace(b'Def="75"', b'Def="90"')
    assert bp.parameter_values(changed)[U.format(2)] == 90.0


def test_invalid_program_yields_nothing():
    assert bp.enumerate_parameters(b"<broken") == []
