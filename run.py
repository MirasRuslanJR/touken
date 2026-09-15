"""Запуск сервера для разработки и демонстрации.

    python run.py                 — только на этом компьютере (127.0.0.1:8000)
    python run.py --lan           — доступен с телефонов в той же Wi-Fi
    python run.py --port 8080     — другой порт
    python run.py --no-reload     — без автоперезапуска (стабильнее для показа)

Режим --lan нужен, чтобы ученики прошли опрос со своих телефонов: ссылка на
127.0.0.1 работает только на самом компьютере, а QR-код с ней бесполезен.
Скрипт сам находит адрес в локальной сети и печатает готовую ссылку.
"""
import argparse
import socket

import uvicorn


def lan_address():
    """IP этого компьютера в локальной сети.

    Соединение UDP никуда не отправляется — оно нужно только чтобы система
    сама выбрала подходящий сетевой интерфейс. Перебирать их вручную сложнее
    и ненадёжнее.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser(description="Запуск «Изолята».")
    parser.add_argument("--lan", action="store_true",
                        help="раздать в локальную сеть, чтобы открыть опрос с телефона")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true",
                        help="не перезапускать при изменении файлов")
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    shown = (lan_address() or "127.0.0.1") if args.lan else "127.0.0.1"
    base = "http://%s:%d" % (shown, args.port)

    # Сообщения запуска намеренно на латинице: консоль Windows по умолчанию не
    # в UTF-8, и кириллица здесь превращается в «РЎРѕР·РґР°СЋ». Само приложение
    # полностью на русском — это только вывод лаунчера.
    print("\n  Izolyat is starting")
    print("  Dashboard: %s" % base)
    if args.lan:
        print("  Open from a phone: same address, phone must be on the same Wi-Fi.")
        print("  If it does not open, Windows Firewall is blocking port %d." % args.port)
        print("  IMPORTANT: open the dashboard at this address, NOT at 127.0.0.1,")
        print("             otherwise the survey link and QR code will point to localhost.")
    print()

    uvicorn.run("app.main:app", host=host, port=args.port, reload=not args.no_reload)


if __name__ == "__main__":
    main()
