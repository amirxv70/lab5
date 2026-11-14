"""ЛР5. Модульные тесты. Запуск из папки lab5: python -m unittest -v"""

import ipaddress
import unittest

import audit
import netcalc


class TestSubnetInfo(unittest.TestCase):
    def test_slash24(self):
        info = netcalc.subnet_info("192.168.10.35/24")
        self.assertEqual(info["Адрес сети"], "192.168.10.0")
        self.assertEqual(info["Broadcast"], "192.168.10.255")
        self.assertEqual(info["Количество узлов"], 254)

    def test_slash30(self):
        info = netcalc.subnet_info("10.0.0.5/30")
        self.assertEqual(info["Количество узлов"], 2)
        self.assertEqual(info["Первый узел"], "10.0.0.5")
        self.assertEqual(info["Последний узел"], "10.0.0.6")

    def test_slash32(self):
        info = netcalc.subnet_info("8.8.8.8/32")
        self.assertEqual(info["Количество узлов"], 0)
        self.assertEqual(info["Первый узел"], "-")

    def test_address_types(self):
        self.assertEqual(netcalc.subnet_info("169.254.1.5/16")["Тип адреса"],
                         "link-local")
        self.assertEqual(netcalc.subnet_info("8.8.8.8/32")["Тип адреса"],
                         "публичный")


class TestParseCidr(unittest.TestCase):
    def test_both_formats_equal(self):
        a = netcalc.parse_cidr("10.0.0.5/26")
        b = netcalc.parse_cidr("10.0.0.5 255.255.255.192")
        self.assertEqual(a, b)

    def test_invalid_address(self):
        with self.assertRaises(ValueError):
            netcalc.parse_cidr("192.168.1.300/24")

    def test_same_subnet(self):
        self.assertTrue(netcalc.same_subnet("10.0.0.5/26", "10.0.0.40"))
        self.assertFalse(netcalc.same_subnet("10.0.0.5/26", "10.0.0.100"))


class TestVlsm(unittest.TestCase):
    DEPS = {"A": 10, "B": 50, "C": 30}

    def test_not_enough_addresses(self):
        with self.assertRaises(ValueError):
            netcalc.vlsm("10.0.0.0/26", {"A": 50, "B": 30})

    def test_with_growth(self):
        self.assertEqual(netcalc.with_growth(60, 10), 66)

    def test_subnets_sorted_by_size_descending(self):
        plan = netcalc.vlsm("10.0.0.0/24", self.DEPS)
        sizes = [p["subnet"].num_addresses for p in plan]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_first_subnet_starts_at_base(self):
        plan = netcalc.vlsm("10.0.0.0/24", self.DEPS)
        self.assertEqual(plan[0]["subnet"].network_address,
                         ipaddress.ip_address("10.0.0.0"))

    def test_check_plan_no_errors(self):
        plan = netcalc.vlsm("10.0.0.0/24", self.DEPS)
        self.assertEqual(netcalc.check_plan("10.0.0.0/24", plan), [])

    def test_min_base_prefix(self):
        net = netcalc.min_base_prefix("10.0.0.0/26", {"A": 50, "B": 30})
        self.assertEqual(net, ipaddress.ip_network("10.0.0.0/25"))

    def test_plan_summary(self):
        plan = netcalc.vlsm("10.0.0.0/24", {"A": 100, "B": 50})
        s = netcalc.plan_summary("10.0.0.0/24", plan)
        self.assertEqual(s["Всего адресов"], 256)
        self.assertEqual(s["Выделено"], 192)
        self.assertEqual(s["Свободно"], 64)


class TestAudit(unittest.TestCase):
    PLAN = {"Офис": ipaddress.ip_network("10.0.0.0/26")}

    @staticmethod
    def dev(host, ip, gw="10.0.0.1"):
        return {"hostname": host, "department": "Офис", "ip": ip, "gateway": gw}

    def codes(self, devices):
        return [code for _, code, _ in audit.audit(self.PLAN, devices)]

    def test_duplicate_ip_e5(self):
        devices = [self.dev("pc1", "10.0.0.10"), self.dev("pc2", "10.0.0.10")]
        self.assertIn("E5", self.codes(devices))

    def test_broadcast_e4(self):
        self.assertIn("E4", self.codes([self.dev("pc1", "10.0.0.63")]))

    def test_clean_device_has_no_problems(self):
        self.assertEqual(self.codes([self.dev("pc1", "10.0.0.10")]), [])


if __name__ == "__main__":
    unittest.main()
