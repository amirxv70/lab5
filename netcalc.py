"""ЛР5. Калькулятор подсетей и планировщик адресного пространства (VLSM)."""

import csv
import ipaddress


def address_type(ip):
    # порядок проверок важен: 169.254.x.x одновременно link-local и private
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_private:
        return "частный"
    return "публичный"


def subnet_info(cidr):
    iface = ipaddress.ip_interface(cidr)
    net = iface.network
    has_hosts = net.num_addresses > 2     # у /31 и /32 обычных узлов нет
    return {
        "Адрес узла": str(iface.ip),
        "Адрес сети": str(net.network_address),
        "Маска": str(net.netmask),
        "Префикс": f"/{net.prefixlen}",
        "Broadcast": str(net.broadcast_address),
        "Первый узел": str(net.network_address + 1) if has_hosts else "-",
        "Последний узел": str(net.broadcast_address - 1) if has_hosts else "-",
        "Количество узлов": net.num_addresses - 2 if has_hosts else 0,
        "Wildcard": str(net.hostmask),
        "Маска (двоичная)": ".".join(f"{b:08b}" for b in net.netmask.packed),
        "Тип адреса": address_type(iface.ip),
    }


def parse_cidr(text):
    """Принимает '10.0.0.5/26' и '10.0.0.5 255.255.255.192'.
    Возвращает ipaddress.ip_interface, при ошибке выбрасывает ValueError."""
    text = text.strip()
    if "/" in text:
        addr, mask = (x.strip() for x in text.split("/", 1))
    else:
        parts = text.split()
        if len(parts) == 2:
            addr, mask = parts
        elif len(parts) == 1:
            try:
                ipaddress.ip_address(parts[0])
            except ValueError:
                raise ValueError(f"неверный адрес: {parts[0]}")
            raise ValueError("не указана маска")
        else:
            raise ValueError("неверный формат ввода")
    try:
        ipaddress.ip_address(addr)
    except ValueError:
        raise ValueError(f"неверный IP-адрес: {addr}")
    try:
        return ipaddress.ip_interface(f"{addr}/{mask}")
    except ValueError:
        raise ValueError(f"недопустимая маска: {mask} "
                         "(у маски единицы должны идти подряд, без разрывов)")


def same_subnet(a, b):
    """a - адрес с маской, b - адрес без маски.
    True, если второй узел находится в подсети первого."""
    iface = parse_cidr(a)
    ip = ipaddress.ip_address(b.strip())
    return ip in iface.network


def with_growth(need, growth):
    """Число устройств с запасом роста growth % (округление вверх)."""
    return (need * (100 + growth) + 99) // 100


def prefix_for(hosts):
    """Минимальный префикс, которого хватит на hosts узлов."""
    prefix = 32
    while 2 ** (32 - prefix) - 2 < hosts:
        prefix -= 1
    return prefix


def vlsm(base_network, departments, growth=0):
    """departments: {название: число_устройств}. Возвращает список словарей."""
    base = ipaddress.ip_network(base_network, strict=False)
    plan = []
    current = base.network_address
    for name, need in sorted(departments.items(), key=lambda x: x[1], reverse=True):
        need_g = with_growth(need, growth)
        subnet = ipaddress.ip_network(f"{current}/{prefix_for(need_g)}")
        if not subnet.subnet_of(base):
            raise ValueError(f"Не хватает адресов для отдела «{name}»")
        plan.append({"name": name, "need": need, "need_g": need_g,
                     "subnet": subnet})
        current = subnet.broadcast_address + 1
    return plan


def plan_summary(base_network, plan):
    """Всего адресов, выделено, свободно, использование в %."""
    base = ipaddress.ip_network(base_network, strict=False)
    total = base.num_addresses
    allocated = sum(p["subnet"].num_addresses for p in plan)
    devices = sum(p["need"] for p in plan)          # реальные устройства, без запаса
    usage = devices / allocated * 100 if allocated else 0
    return {
        "Всего адресов": total,
        "Выделено": allocated,
        "Свободно": total - allocated,
        "Использование, %": round(usage, 1),
    }


def check_plan(base_network, plan):
    """Список ошибок. Пустой список - план корректен."""
    base = ipaddress.ip_network(base_network, strict=False)
    errors = []
    for p in plan:
        if not p["subnet"].subnet_of(base):
            errors.append(f"Подсеть {p['subnet']} отдела «{p['name']}» "
                          f"выходит за пределы {base}")
    for i in range(len(plan)):
        for j in range(i + 1, len(plan)):
            if plan[i]["subnet"].overlaps(plan[j]["subnet"]):
                errors.append(f"Подсети отделов «{plan[i]['name']}» "
                              f"({plan[i]['subnet']}) и «{plan[j]['name']}» "
                              f"({plan[j]['subnet']}) пересекаются")
    return errors


def min_base_prefix(base_network, departments, growth=0):
    """Если адресов не хватает - первая (наименьшая) сеть, в которую
    план помещается: префикс уменьшаем на 1, пока не поместится."""
    base = ipaddress.ip_network(base_network, strict=False)
    for prefix in range(base.prefixlen, -1, -1):
        net = ipaddress.ip_network(f"{base.network_address}/{prefix}",
                                   strict=False)
        try:
            vlsm(net, departments, growth)
            return net
        except ValueError:
            continue
    return None


def summarize(plan):
    """Возвращает (результат collapse_addresses, наименьшая общая надсеть)."""
    subnets = [p["subnet"] for p in plan]
    collapsed = list(ipaddress.collapse_addresses(subnets))
    common = subnets[0]
    while not all(s.subnet_of(common) for s in subnets):
        common = common.supernet()
    return collapsed, common


def parse_departments(text):
    """'Продажи=60, Склад=25' -> {'Продажи': 60, 'Склад': 25}"""
    deps = {}
    for part in text.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f"ожидается вид «Отдел=число», получено: {part.strip()}")
        name, value = part.rsplit("=", 1)
        name = name.strip()
        if not name:
            raise ValueError("пустое название отдела")
        try:
            number = int(value)
        except ValueError:
            raise ValueError(f"не число: {value.strip()}")
        if number <= 0:
            raise ValueError(f"число устройств должно быть больше 0: {name}")
        deps[name] = number
    if not deps:
        raise ValueError("не указано ни одного отдела")
    return deps


def run_vlsm_dialog():
    """Пункт 3 меню."""
    base = ipaddress.ip_network(input("Базовая сеть (например 10.10.0.0/24): ").strip(),
                                strict=False)
    try:
        growth = int(input("Запас роста, %: ").strip())
    except ValueError:
        raise ValueError("запас роста должен быть целым числом")
    if growth < 0:
        raise ValueError("запас роста не может быть отрицательным")
    deps = parse_departments(input("Отделы (Продажи=60, Склад=25, ...): "))
    variant = input("Номер варианта N: ").strip() or "N"

    try:
        plan = vlsm(base, deps, growth)
    except ValueError as e:
        print("Ошибка:", e)
        suggested = min_base_prefix(base, deps, growth)
        if suggested:
            print(f"Адресов в сети {base} не хватает. "
                  f"Подойдёт сеть: {suggested}")
        return

    print_plan(plan)
    print()
    for k, v in plan_summary(base, plan).items():
        print(f"{k:18}: {v}")
    errors = check_plan(base, plan)
    print("\nПроверка плана:", "ошибок нет" if not errors else "")
    for e in errors:
        print("  -", e)
    collapsed, common = summarize(plan)
    print("Агрегированные маршруты:", ", ".join(map(str, collapsed)))
    print("Наименьшая общая надсеть:", common)
    path = f"plan_v{variant}.csv"
    save_plan_csv(plan, path)
    print(f"План сохранён в {path}")


def save_plan_csv(plan, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["department", "need", "need_with_growth", "subnet",
                    "gateway", "broadcast"])
        for p in plan:
            net = p["subnet"]
            w.writerow([p["name"], p["need"], p["need_g"], net,
                        net.network_address + 1, net.broadcast_address])


def print_plan(plan):
    print(f"\n{'Отдел':22}{'Нужно':>6}{'+запас':>8}  "
          f"{'Подсеть':20}{'Диапазон':34}Broadcast")
    for p in plan:
        net = p["subnet"]
        rng = f"{net.network_address + 1} - {net.broadcast_address - 1}"
        print(f"{p['name']:22}{p['need']:>6}{p['need_g']:>8}  "
              f"{str(net):20}{rng:34}{net.broadcast_address}")


def menu():
    try:
        while True:
            print("\n==== Сетевой калькулятор ====")
            print("1 - Информация о подсети")
            print("2 - Находятся ли два узла в одной подсети")
            print("3 - План VLSM для своего варианта")
            print("0 - Выход")
            choice = input("Ваш выбор: ").strip()
            try:
                if choice == "1":
                    iface = parse_cidr(input("Адрес с маской: "))
                    for k, v in subnet_info(str(iface)).items():
                        print(f"{k:18}: {v}")
                elif choice == "2":
                    a = input("Первый узел с маской: ")
                    b = input("Второй узел (без маски): ")
                    print("В одной подсети" if same_subnet(a, b)
                          else "В разных подсетях")
                elif choice == "3":
                    run_vlsm_dialog()
                elif choice == "0":
                    break
                else:
                    print("Нет такого пункта меню")
            except ValueError as e:
                print("Ошибка:", e)
    except (KeyboardInterrupt, EOFError):
        pass
    print("\nРабота завершена")


if __name__ == "__main__":
    menu()
