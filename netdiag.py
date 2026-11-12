"""ЛР5. Автоматическая пошаговая диагностика сети."""

import csv
import datetime
import os
import platform
import re
import socket
import subprocess
import time

SYSTEM = platform.system()          # "Windows", "Linux" или "Darwin" (macOS)
IS_WINDOWS = SYSTEM == "Windows"
LOG_FILE = "diag_log.csv"

# time=12.3 ms | time<1ms | время=12мс | время<1мс (русская Windows)
PING_TIME_RE = re.compile(r"(?:time|время)\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*(?:ms|мс)",
                          re.IGNORECASE)


def run(cmd, timeout=15):
    """Запускает команду и возвращает (код возврата, вывод)."""
    try:
        enc = "cp866" if IS_WINDOWS else "utf-8"   # кодировка консоли Windows
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding=enc, errors="replace")
        return r.returncode, r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return -1, ""


def parse_ping_times(out):
    """Список времён ответа (мс) из вывода ping."""
    return [float(t.replace(",", ".")) for t in PING_TIME_RE.findall(out)]


def ping(host, count=3):
    """Возвращает (успех, среднее время в мс или None).
    Успех - только если найдено хотя бы одно время ответа: на Windows ping
    возвращает код 0 и при ответе «Заданный узел недоступен»."""
    flag = "-n" if IS_WINDOWS else "-c"
    _, out = run(["ping", flag, str(count), host])
    times = parse_ping_times(out)
    if not times:
        return False, None
    return True, round(sum(times) / len(times), 1)


def parse_gateway_windows(out):
    """Из вывода 'route print -4 0.0.0.0' берёт шлюз с наименьшей метрикой."""
    routes = re.findall(
        r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s+"
        r"\d+\.\d+\.\d+\.\d+\s+(\d+)", out, re.MULTILINE)
    if not routes:
        return None
    return min(routes, key=lambda r: int(r[1]))[0]


def get_default_gateway():
    """Определяет шлюз по умолчанию. Возвращает строку с IP или None."""
    if SYSTEM == "Linux":
        _, out = run(["ip", "route"])
        m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    if SYSTEM == "Windows":
        _, out = run(["route", "print", "-4", "0.0.0.0"])
        return parse_gateway_windows(out)
    if SYSTEM == "Darwin":
        _, out = run(["route", "-n", "get", "default"])
        m = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    return None


def resolve(domain):
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None


def tcp_check(host, port, timeout=3):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return False, None


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # пакеты не отправляются, выбирается маршрут
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# рекомендации для Windows; ключи совпадают с названиями шагов в main()
ADVICE = {
    "Собственный интерфейс": [
        "Проверьте, включён ли адаптер (Wi-Fi / Ethernet) и подключён ли кабель",
        "Посмотрите настройки адаптера: ipconfig /all",
        "Обновите адрес: ipconfig /release, затем ipconfig /renew",
    ],
    "Шлюз по умолчанию": [
        "Проверьте подключение к роутеру: Wi-Fi подключён, кабель вставлен",
        "Проверьте адрес шлюза командой ipconfig (строка «Основной шлюз»)",
        "Перезагрузите роутер и повторите диагностику",
    ],
    "Внешняя сеть по IP (8.8.8.8)": [
        "Шлюз отвечает, но выхода в интернет нет: проверьте, оплачен ли интернет",
        "Проверьте маршрут до внешней сети: tracert 8.8.8.8",
        "Позвоните провайдеру или проверьте настройки роутера",
    ],
    "DNS (google.com)": [
        "Интернет по IP есть, но имена не определяются: проверьте адрес DNS "
        "(ipconfig /all, строка «DNS-серверы»)",
        "Сбросьте кэш DNS: ipconfig /flushdns",
        "Попробуйте другой DNS-сервер, например 8.8.8.8 или 1.1.1.1",
    ],
    "Веб-сервис (google.com:443)": [
        "Проверьте, не блокирует ли порт 443 брандмауэр или антивирус",
        "Проверьте доступность порта вручную: Test-NetConnection google.com -Port 443",
        "Отключите VPN или прокси и повторите диагностику",
    ],
}


def log_result(step, ok, ms):
    """Дописывает строку в LOG_FILE: дата и время, компьютер, локальный IP,
    шаг, OK/FAIL, время в мс. Если файла нет - сначала заголовок."""
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["datetime", "hostname", "local_ip", "step", "result", "ms"])
        w.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    socket.gethostname(), get_local_ip(), step,
                    "OK" if ok else "FAIL", "" if ms is None else ms])


def main():
    gateway = get_default_gateway()
    if gateway is None:
        gateway = input("Шлюз не определён. Введите IP шлюза: ").strip()
    print(f"Локальный IP: {get_local_ip()}   Шлюз: {gateway}\n")
    steps = [
        ("Стек TCP/IP (127.0.0.1)", lambda: ping("127.0.0.1")),
        ("Собственный интерфейс", lambda: ping(get_local_ip())),
        ("Шлюз по умолчанию", lambda: ping(gateway)),
        ("Внешняя сеть по IP (8.8.8.8)", lambda: ping("8.8.8.8")),
        ("DNS (google.com)", lambda: (resolve("google.com") is not None, None)),
        ("Веб-сервис (google.com:443)", lambda: tcp_check("google.com", 443)),
    ]
    for name, check in steps:
        ok, ms = check()
        log_result(name, ok, ms)
        extra = "" if ms is None else f"{ms} мс"
        print(f"[{'OK' if ok else 'FAIL'}] {name:32} {extra}")
        if not ok:
            print(f"\nДиагностика остановлена. Проблема на уровне: {name}")
            for tip in ADVICE.get(name, []):
                print("  -", tip)
            return
    print("\nВсе уровни работают.")


if __name__ == "__main__":
    main()
