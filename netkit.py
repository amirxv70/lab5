"""ЛР5. Единая утилита командной строки.

Примеры:
  python netkit.py calc 10.0.0.5/26
  python netkit.py vlsm 10.10.0.0/24 "Продажи=60" "Склад=25" --growth 25 --csv p.csv
  python netkit.py audit plan.csv devices.csv
  python netkit.py diag
  python netkit.py services --parallel

Коды завершения: 0 - всё в порядке, 1 - найдены проблемы.
"""

import argparse
import ipaddress
import time

import audit
import netcalc
import netdiag
import services


def cmd_calc(args):
    try:
        iface = netcalc.parse_cidr(args.address)
    except ValueError as e:
        print("Ошибка:", e)
        return 1
    for k, v in netcalc.subnet_info(str(iface)).items():
        print(f"{k:18}: {v}")
    return 0


def cmd_vlsm(args):
    try:
        base = ipaddress.ip_network(args.base, strict=False)
        deps = netcalc.parse_departments(",".join(args.departments))
        if args.growth < 0:
            raise ValueError("запас роста не может быть отрицательным")
    except ValueError as e:
        print("Ошибка:", e)
        return 1
    try:
        plan = netcalc.vlsm(base, deps, args.growth)
    except ValueError as e:
        print("Ошибка:", e)
        suggested = netcalc.min_base_prefix(base, deps, args.growth)
        if suggested:
            print(f"Адресов в сети {base} не хватает. Подойдёт сеть: {suggested}")
        return 1

    netcalc.print_plan(plan)
    print()
    for k, v in netcalc.plan_summary(base, plan).items():
        print(f"{k:18}: {v}")
    errors = netcalc.check_plan(base, plan)
    for e in errors:
        print("Ошибка плана:", e)
    collapsed, common = netcalc.summarize(plan)
    print("Агрегированные маршруты:", ", ".join(map(str, collapsed)))
    print("Наименьшая общая надсеть:", common)
    if args.csv:
        netcalc.save_plan_csv(plan, args.csv)
        print(f"План сохранён в {args.csv}")
    return 1 if errors else 0


def cmd_audit(args):
    try:
        errors = audit.run_audit(args.plan, args.devices, args.report)
    except (OSError, KeyError, ValueError) as e:
        print("Ошибка:", e)
        return 1
    return 1 if errors else 0


def cmd_diag(args):
    return netdiag.main(args.gateway)


def cmd_services(args):
    t0 = time.perf_counter()
    if args.parallel:
        results = services.check_all_parallel(services.SERVICES, args.workers,
                                              args.timeout)
    else:
        results = services.check_all_sequential(services.SERVICES, args.timeout)
    elapsed = time.perf_counter() - t0
    services.print_table(results)
    mode = f"параллельно, workers = {args.workers}" if args.parallel else "последовательно"
    print(f"\nВремя ({mode}): {elapsed:.2f} с")
    return 0 if all(r["status"] == "OPEN" for r in results) else 1


def main():
    parser = argparse.ArgumentParser(description="Сетевые утилиты ЛР5")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("calc", help="калькулятор подсети")
    p.add_argument("address", help="10.0.0.5/26 или '10.0.0.5 255.255.255.192'")
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("vlsm", help="план VLSM с запасом роста")
    p.add_argument("base", help="базовая сеть, например 10.10.0.0/24")
    p.add_argument("departments", nargs="+", help="отделы вида Название=число")
    p.add_argument("--growth", type=int, default=0, help="запас роста, %%")
    p.add_argument("--csv", metavar="FILE", help="сохранить план в CSV")
    p.set_defaults(func=cmd_vlsm)

    p = sub.add_parser("audit", help="аудит IP-адресов устройств")
    p.add_argument("plan", help="CSV с планом адресации")
    p.add_argument("devices", help="CSV со списком устройств")
    p.add_argument("--report", metavar="FILE", default="audit_report.csv",
                   help="куда сохранить отчёт (по умолчанию audit_report.csv)")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("diag", help="пошаговая диагностика сети")
    p.add_argument("--gateway", metavar="IP",
                   help="шлюз (если не указан, определяется автоматически)")
    p.set_defaults(func=cmd_diag)

    p = sub.add_parser("services", help="проверка сетевых сервисов")
    p.add_argument("--parallel", action="store_true", help="параллельная проверка")
    p.add_argument("--workers", type=int, default=10, help="число потоков")
    p.add_argument("--timeout", type=float, default=3, help="таймаут, с")
    p.set_defaults(func=cmd_services)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
