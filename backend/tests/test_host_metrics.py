import unittest

from app.services import host_metrics


STAT_A = """cpu  100 0 50 850 0 0 0 0
cpu0 50 0 25 425 0 0 0 0
cpu1 50 0 25 425 0 0 0 0
intr 0
"""
STAT_B = """cpu  200 0 100 900 0 0 0 0
cpu0 100 0 50 450 0 0 0 0
cpu1 100 0 50 450 0 0 0 0
intr 0
"""
MEMINFO = """MemTotal:        8000000 kB
MemFree:         1000000 kB
MemAvailable:    4000000 kB
SwapTotal:       2000000 kB
SwapFree:        1500000 kB
"""
NETDEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  ens3: 1000       1    0    0    0     0          0         0 2000       1    0    0    0     0       0          0
    lo: 10         1    0    0    0     0          0         0 10         1    0    0    0     0       0          0
   wg0: 500        1    2    0    0     0          0         0 800        1    0    1    0     0       0          0
"""
DISKSTATS = """   8       0 sda 1 0 100 0 1 0 200 0 0 0 0 0 0 0 0
   8       1 sda1 1 0 50 0 1 0 80 0 0 0 0 0 0 0 0
   7       0 loop0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
"""


class HostMetricsParseTests(unittest.TestCase):
    def test_cpu_percent_from_two_samples(self) -> None:
        a, per_a = host_metrics.parse_cpu_stat(STAT_A)
        b, per_b = host_metrics.parse_cpu_stat(STAT_B)
        self.assertEqual(a, (850, 1000))
        self.assertEqual(len(per_a), 2)
        self.assertEqual(host_metrics.cpu_percent(a, b), 75.0)
        self.assertIsNone(host_metrics.cpu_percent(None, b))
        self.assertEqual(host_metrics.cpu_percent(per_a[0], per_b[0]), 75.0)

    def test_meminfo_available_and_swap(self) -> None:
        mem = host_metrics.parse_meminfo(MEMINFO)
        self.assertEqual(mem["MemTotal"], 8000000 * 1024)
        self.assertEqual(mem["MemAvailable"], 4000000 * 1024)
        self.assertEqual(mem["SwapTotal"], 2000000 * 1024)

    def test_netdev_parses_interfaces(self) -> None:
        rows = host_metrics.parse_netdev(NETDEV)
        names = [row["name"] for row in rows]
        self.assertEqual(names, ["ens3", "lo", "wg0"])
        wg = next(row for row in rows if row["name"] == "wg0")
        self.assertEqual(wg["rx_bytes"], 500)
        self.assertEqual(wg["tx_bytes"], 800)
        self.assertEqual(wg["rx_errors"], 2)

    def test_diskstats_skips_partitions_and_loop(self) -> None:
        read, write = host_metrics.parse_diskstats(DISKSTATS)
        self.assertEqual(read, 100)
        self.assertEqual(write, 200)

    def test_collect_returns_host_snapshot(self) -> None:
        host_metrics.reset_metrics_state()
        snap = host_metrics.collect_host_metrics()
        self.assertTrue(snap["hostname"])
        self.assertGreaterEqual(snap["cpu"]["cores"], 1)
        self.assertIn("percent", snap["memory"])
        self.assertGreater(snap["memory"]["total_bytes"], 0)
        self.assertIsInstance(snap["disks"], list)
        self.assertIsInstance(snap["network"], list)
        second = host_metrics.collect_host_metrics()
        self.assertGreaterEqual(second["cpu"]["cores"], 1)
        host_metrics.reset_metrics_state()
