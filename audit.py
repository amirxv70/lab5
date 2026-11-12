"""ЛР5. Аудит IP-адресов устройств по плану адресации."""

import csv
import ipaddress
import sys


def load_plan(path):
    """plan.csv -> {отдел: IPv4Network}"""
    with open(path, encoding="utf-8") as f:
        return {row["department"]: ipaddress.ip_network(row["subnet"])
                for row in csv.DictReader(f)}


def load_devices(path):
    """devices.csv: hostname,department,ip,gateway"""
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def audit(plan, devices):
    """Возвращает список кортежей (hostname, код, описание)."""
    problems = []
    seen_ips = {}
    for d in devices:
        host = d["hostname"]
        try:
            ip = ipaddress.ip_address(d["ip"].strip())
        except ValueError:
            problems.append((host, "E1", f"неверный формат IP: {d['ip']}"))
            continue

        # E5 - дубликат IP: адрес уже занят другим устройством
        if ip in seen_ips:
            problems.append((host, "E5",
                             f"{ip} уже занят устройством {seen_ips[ip]}"))
        else:
            seen_ips[ip] = host

        net = plan.get(d["department"])
        if net is None:
            problems.append((host, "E2", f"неизвестный отдел: {d['department']}"))
            continue
        if ip not in net:
            problems.append((host, "E3", f"{ip} не входит в подсеть отдела {net}"))
        # E4 - адрес сети или broadcast
        if ip == net.network_address:
            problems.append((host, "E4", f"{ip} - адрес сети {net}"))
        elif ip == net.broadcast_address:
            problems.append((host, "E4", f"{ip} - broadcast подсети {net}"))

        # шлюз: E1 (формат), E6 (вне подсети), E7 (равен IP узла), W1
        try:
            gw = ipaddress.ip_address(d["gateway"].strip())
        except ValueError:
            problems.append((host, "E1", f"неверный формат шлюза: {d['gateway']}"))
            continue
        if gw not in net:
            problems.append((host, "E6", f"шлюз {gw} вне подсети отдела {net}"))
        elif gw == ip:
            problems.append((host, "E7", f"шлюз {gw} совпадает с IP узла"))
        elif gw != net.network_address + 1:
            problems.append((host, "W1",
                             f"шлюз {gw} не первый адрес подсети "
                             f"({net.network_address + 1})"))
    return problems


def save_report(problems, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["hostname", "code", "description"])
        w.writerows(problems)


def run_audit(plan_file, dev_file, report_file="audit_report.csv"):
    """Печатает замечания и итог, сохраняет отчёт. Возвращает число ошибок."""
    devices = load_devices(dev_file)
    problems = audit(load_plan(plan_file), devices)
    for host, code, text in problems:
        print(f"[{code}] {host:15} {text}")
    errors = sum(1 for p in problems if p[1].startswith("E"))
    warnings = sum(1 for p in problems if p[1].startswith("W"))
    bad_hosts = {p[0] for p in problems}
    clean = sum(1 for d in devices if d["hostname"] not in bad_hosts)
    print(f"\nПроверено устройств: {len(devices)}, ошибок: {errors}, "
          f"предупреждений: {warnings}, без замечаний: {clean}")
    save_report(problems, report_file)
    print(f"Замечания сохранены в {report_file}")
    return errors


if __name__ == "__main__":
    plan_file = sys.argv[1] if len(sys.argv) > 1 else "plan.csv"
    dev_file = sys.argv[2] if len(sys.argv) > 2 else "devices.csv"
    run_audit(plan_file, dev_file)
