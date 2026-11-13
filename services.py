"""ЛР5. Параллельная проверка доступности сетевых сервисов."""

import socket
import time
from concurrent.futures import ThreadPoolExecutor

from netdiag import get_default_gateway

GATEWAY = get_default_gateway() or "192.168.1.1"

SERVICES = [
    ("Google HTTPS", "google.com", 443),
    ("GitHub SSH", "github.com", 22),
    ("Google DNS", "8.8.8.8", 53),
    ("Cloudflare DNS", "1.1.1.1", 53),
    ("Локальный веб-сервер", "127.0.0.1", 8030),       # порт варианта 3
    ("Закрытый локальный порт", "127.0.0.1", 8031),    # порт варианта + 1
    ("Несуществующий домен", "no-such-host.example", 80),
    ("Фильтруемый адрес", "10.255.255.1", 80),
    # свои сервисы
    ("Сайт университета", "satbayev.university", 443),
    ("Веб-интерфейс шлюза", GATEWAY, 80),
    ("Почта Gmail IMAP", "imap.gmail.com", 993),
    ("DNS шлюза", GATEWAY, 53),
]


def check_service(name, host, port, timeout=3):
    """Возвращает словарь: name, host, port, status, ms, addresses."""
    result = {"name": name, "host": host, "port": port,
              "status": "?", "ms": None, "addresses": []}
    # 1) все адреса узла
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        result["status"] = "DNS-ERROR"
        return result
    result["addresses"] = sorted({info[4][0] for info in infos})

    # 2) попытка подключения с замером времени
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout):
            result["status"] = "OPEN"
    except ConnectionRefusedError:
        result["status"] = "REFUSED"
    except TimeoutError:                      # socket.timeout
        result["status"] = "TIMEOUT"
    except OSError:
        result["status"] = "ERROR"
    result["ms"] = round((time.perf_counter() - start) * 1000, 1)
    return result


def check_all_sequential(services):
    return [check_service(*s) for s in services]


def check_all_parallel(services, workers=10):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda s: check_service(*s), services))


def print_table(results):
    print(f"{'Сервис':26}{'Узел':22}{'Порт':>6}  {'Статус':10}{'мс':>8}  Адресов")
    for r in results:
        ms = "" if r["ms"] is None else r["ms"]
        print(f"{r['name']:26}{r['host']:22}{r['port']:>6}  {r['status']:10}"
              f"{ms:>8}  {len(r['addresses'])}")


if __name__ == "__main__":
    t0 = time.perf_counter()
    res = check_all_sequential(SERVICES)
    t1 = time.perf_counter()
    print_table(res)
    print(f"\nПоследовательно: {t1 - t0:.2f} с")

    print("\nПараллельная проверка:")
    for workers in (1, 2, 5, 10, 20):
        t0 = time.perf_counter()
        check_all_parallel(SERVICES, workers)
        print(f"workers = {workers:<3}: {time.perf_counter() - t0:.2f} с")
