import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


def _load_tools_status():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "vmware"
        / "tools_status.py"
    )
    spec = importlib.util.spec_from_file_location("tools_status_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tools_status = _load_tools_status()


class VMwareToolsStatusTests(unittest.TestCase):
    def test_2016_template_offline_has_tools(self) -> None:
        guest = SimpleNamespace(toolsVersion="11265", toolsStatus="toolsNotRunning")
        self.assertFalse(tools_status.is_vmware_tools_missing(guest))

    def test_2019_template_without_tools(self) -> None:
        guest = SimpleNamespace(toolsVersion="0", toolsStatus="toolsNotInstalled")
        self.assertTrue(tools_status.is_vmware_tools_missing(guest))

    def test_running_tools_ok(self) -> None:
        guest = SimpleNamespace(toolsVersion=11265, toolsStatus="toolsOk")
        self.assertFalse(tools_status.is_vmware_tools_missing(guest))

    def test_unknown_guest_keeps_waiting(self) -> None:
        self.assertFalse(tools_status.is_vmware_tools_missing(None))

    def test_tools_version_int(self) -> None:
        self.assertEqual(tools_status.tools_version_int("11265"), 11265)
        self.assertEqual(tools_status.tools_version_int(None), 0)
        self.assertEqual(tools_status.tools_version_int("x"), 0)

    def test_assert_blocks_template_without_tools(self) -> None:
        vm = SimpleNamespace(
            name="VPS-BASE-SV2019",
            guest=SimpleNamespace(toolsVersion=0, toolsStatus="toolsNotInstalled"),
        )
        with self.assertRaises(RuntimeError) as raised:
            tools_status.assert_template_has_vmware_tools(vm)
        self.assertIn("VPS-BASE-SV2019", str(raised.exception))
        text = str(raised.exception)
        self.assertIn("agente de gerenciamento", text)
        self.assertNotIn("VMware", text)
        self.assertNotIn("ESXi", text)


if __name__ == "__main__":
    unittest.main()
