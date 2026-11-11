import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.services.pricing import (
    calculate_flexible_price,
    calculate_new_order_price,
    calculate_upgrade_monthly_delta,
    compute_monthly_price,
)


def _plan(**overrides):
    data = dict(
        id=1,
        default_disk_gb=30,
        monthly_base_cents=0,
        price_per_vcpu_cents=800,
        price_per_gb_ram_cents=800,
        price_per_gb_disk_cents=100,
        min_vcpu=2,
        max_vcpu=12,
        min_ram_mb=2048,
        max_ram_mb=12288,
        max_disk_gb=200,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def _instance(**overrides):
    data = dict(
        vcpu=2,
        ram_mb=2048,
        disk_gb=30,
        custom_monthly_cents=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


class UnitPricingTests(unittest.TestCase):
    def test_custom_price_has_no_monthly_base(self) -> None:
        plan = _plan()
        price = compute_monthly_price(plan, vcpu=1, ram_mb=1024, disk_gb=30)
        self.assertEqual(price, 1600)

    def test_one_extra_gb_ram_adds_only_unit_price(self) -> None:
        plan = _plan()
        one_gb = compute_monthly_price(plan, vcpu=1, ram_mb=1024, disk_gb=30)
        two_gb = compute_monthly_price(plan, vcpu=1, ram_mb=2048, disk_gb=30)
        self.assertEqual(two_gb - one_gb, plan.price_per_gb_ram_cents)

    def test_one_extra_vcpu_adds_only_unit_price(self) -> None:
        plan = _plan()
        one = compute_monthly_price(plan, vcpu=1, ram_mb=1024, disk_gb=30)
        two = compute_monthly_price(plan, vcpu=2, ram_mb=1024, disk_gb=30)
        self.assertEqual(two - one, plan.price_per_vcpu_cents)

    def test_included_disk_is_free(self) -> None:
        plan = _plan()
        base = compute_monthly_price(plan, vcpu=1, ram_mb=1024, disk_gb=30)
        same = compute_monthly_price(plan, vcpu=1, ram_mb=1024, disk_gb=30)
        extra = compute_monthly_price(plan, vcpu=1, ram_mb=1024, disk_gb=31)
        self.assertEqual(base, same)
        self.assertEqual(extra - base, plan.price_per_gb_disk_cents)

    def test_upgrade_one_gb_ram_is_unit_only(self) -> None:
        plan = _plan()
        instance = _instance(vcpu=2, ram_mb=2048, disk_gb=50)
        delta = calculate_upgrade_monthly_delta(
            plan, instance, target_vcpu=2, target_ram_mb=3072, target_disk_gb=50
        )
        self.assertEqual(delta, 800)

    def test_upgrade_ignores_preset_reprice(self) -> None:
        plan = _plan()
        instance = _instance(vcpu=2, ram_mb=2048, disk_gb=50)
        preset = SimpleNamespace(
            plan_id=1,
            is_active=True,
            vcpu=2,
            ram_mb=2048,
            disk_gb=50,
            price_cents=5990,
        )
        delta = calculate_upgrade_monthly_delta(
            plan,
            instance,
            target_vcpu=2,
            target_ram_mb=3072,
            target_disk_gb=50,
            plan_presets=[preset],
        )
        self.assertEqual(delta, 800)

    def test_flexible_above_preset_adds_units_only(self) -> None:
        plan = _plan()
        preset = SimpleNamespace(vcpu=2, ram_mb=2048, disk_gb=50, price_cents=5990)
        price = calculate_flexible_price(
            plan, vcpu=2, ram_mb=3072, disk_gb=50, preset=preset
        )
        self.assertEqual(price, 5990 + 800)

    def test_upgrade_rejects_no_change(self) -> None:
        plan = _plan()
        instance = _instance()
        with self.assertRaises(HTTPException) as ctx:
            calculate_upgrade_monthly_delta(
                plan,
                instance,
                target_vcpu=instance.vcpu,
                target_ram_mb=instance.ram_mb,
                target_disk_gb=instance.disk_gb,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_order_uses_package_then_unit_extras(self) -> None:
        plan = _plan()
        starter = SimpleNamespace(
            plan_id=1,
            is_active=True,
            vcpu=2,
            ram_mb=2048,
            disk_gb=40,
            price_cents=4990,
        )
        gamer = SimpleNamespace(
            plan_id=1,
            is_active=True,
            vcpu=4,
            ram_mb=4096,
            disk_gb=60,
            price_cents=7490,
        )
        presets = [starter, gamer]
        exact = calculate_new_order_price(
            plan, 2, 2048, 40, plan_presets=presets
        )
        extra_ram = calculate_new_order_price(
            plan, 2, 3072, 40, plan_presets=presets
        )
        between = calculate_new_order_price(
            plan, 3, 3072, 40, plan_presets=presets
        )
        self.assertEqual(exact, 4990)
        self.assertEqual(extra_ram, 4990 + 800)
        self.assertEqual(between, 4990 + 800 + 800)

    def test_semi_package_8_8(self) -> None:
        plan = _plan(id=2)
        starter = SimpleNamespace(
            plan_id=2,
            is_active=True,
            vcpu=8,
            ram_mb=8192,
            disk_gb=120,
            price_cents=17990,
        )
        price = calculate_new_order_price(
            plan, 8, 8192, 120, plan_presets=[starter]
        )
        extra = calculate_new_order_price(
            plan, 9, 8192, 120, plan_presets=[starter]
        )
        self.assertEqual(price, 17990)
        self.assertEqual(extra, 17990 + 800)

    def test_same_custom_spec_vps_not_pricier_than_semi(self) -> None:
        from app.services.plan_presets import SEMI_PRESETS, VPS_PRESETS

        vps = _plan(id=1, max_vcpu=12, max_ram_mb=12288, max_disk_gb=200)
        semi = _plan(
            id=2,
            min_vcpu=8,
            max_vcpu=24,
            min_ram_mb=8192,
            max_ram_mb=32768,
            max_disk_gb=500,
        )
        vps_presets = [
            SimpleNamespace(plan_id=1, is_active=True, **p) for p in VPS_PRESETS
        ]
        semi_presets = [
            SimpleNamespace(plan_id=2, is_active=True, **p) for p in SEMI_PRESETS
        ]
        specs = [
            (8, 8192, 80),
            (8, 8192, 120),
            (8, 8192, 160),
            (9, 9216, 120),
            (12, 12288, 100),
            (12, 12288, 160),
        ]
        for vcpu, ram_mb, disk_gb in specs:
            vps_price = calculate_new_order_price(
                vps, vcpu, ram_mb, disk_gb, plan_presets=vps_presets
            )
            semi_price = calculate_new_order_price(
                semi, vcpu, ram_mb, disk_gb, plan_presets=semi_presets
            )
            self.assertLessEqual(
                vps_price,
                semi_price,
                f"{vcpu}/{ram_mb // 1024}/{disk_gb}: VPS {vps_price} > Semi {semi_price}",
            )

    def test_classify_upgrade_rejects_downgrade(self) -> None:
        from app.services.pricing import classify_upgrade_direction

        self.assertEqual(
            classify_upgrade_direction(
                current_vcpu=8,
                current_ram_mb=8192,
                current_disk_gb=80,
                current_network_mbps=300,
                target_vcpu=4,
                target_ram_mb=4096,
                target_disk_gb=60,
                target_network_mbps=300,
            ),
            "downgrade",
        )
        self.assertEqual(
            classify_upgrade_direction(
                current_vcpu=8,
                current_ram_mb=8192,
                current_disk_gb=120,
                current_network_mbps=500,
                target_vcpu=12,
                target_ram_mb=12288,
                target_disk_gb=100,
                target_network_mbps=300,
            ),
            "downgrade",
        )
        self.assertEqual(
            classify_upgrade_direction(
                current_vcpu=8,
                current_ram_mb=8192,
                current_disk_gb=80,
                current_network_mbps=300,
                target_vcpu=8,
                target_ram_mb=8192,
                target_disk_gb=120,
                target_network_mbps=500,
            ),
            "upgrade",
        )
        self.assertEqual(
            classify_upgrade_direction(
                current_vcpu=8,
                current_ram_mb=8192,
                current_disk_gb=80,
                current_network_mbps=300,
                target_vcpu=8,
                target_ram_mb=8192,
                target_disk_gb=80,
                target_network_mbps=300,
            ),
            "same",
        )


if __name__ == "__main__":
    unittest.main()
