#!/usr/bin/env python3
"""Простий аналог top для Linux. Дані беремо з /proc.

Клавіші: q - вихід, c - сортувати за CPU, m - сортувати за пам'яттю.
"""

import curses
import os
import pwd
import time

CLK_TCK = os.sysconf("SC_CLK_TCK")  # скільки "тіків" CPU в секунді
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")  # розмір сторінки пам'яті в байтах
INTERVAL = 2.0  # як часто оновлювати екран (сек)


def read_cpu():
    """Повертає (всього_тіків, тіків_простою) для всієї системи."""
    with open("/proc/stat") as f:
        values = [int(x) for x in f.readline().split()[1:]]
    idle = values[3] + values[4]  # idle + iowait
    return sum(values), idle


def read_mem():
    """Повертає (всього, використано) у кБ."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, value = line.split(":")
            info[key] = int(value.split()[0])
    total = info["MemTotal"]
    return total, total - info["MemAvailable"]


def read_processes():
    """Повертає словник {pid: (ім'я, користувач, стан, тіки_cpu, rss_байт)}."""
    result = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as f:
                data = f.read()
            # Ім'я процесу стоїть у дужках і може містити пробіли,
            # тому шукаємо останню закриваючу дужку.
            name = data[data.index("(") + 1 : data.rindex(")")]
            rest = data[data.rindex(")") + 2 :].split()
            state = rest[0]
            ticks = int(rest[11]) + int(rest[12])  # utime + stime
            rss = int(rest[21]) * PAGE_SIZE
            uid = os.stat(f"/proc/{entry}").st_uid
            try:
                user = pwd.getpwuid(uid).pw_name
            except KeyError:
                user = str(uid)
            result[int(entry)] = (name, user, state, ticks, rss)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue  # процес міг завершитися, поки ми його читали
    return result


def fmt_uptime():
    with open("/proc/uptime") as f:
        seconds = int(float(f.read().split()[0]))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    return f"{days}д {hours}г {rem // 60}хв"


def main(stdscr):
    curses.curs_set(0)
    stdscr.timeout(100)  # getch чекає максимум 0.1 сек

    sort_by = "cpu"
    prev_cpu = read_cpu()
    prev_procs = read_processes()
    prev_time = time.time()
    last_draw = 0.0

    while True:
        key = stdscr.getch()
        if key == ord("q"):
            break
        elif key == ord("c"):
            sort_by = "cpu"
        elif key == ord("m"):
            sort_by = "mem"

        now = time.time()
        if now - last_draw < INTERVAL and key == -1:
            continue

        # --- Рахуємо навантаження ---
        total, idle = read_cpu()
        d_total = total - prev_cpu[0]
        d_idle = idle - prev_cpu[1]
        cpu_percent = 100 * (d_total - d_idle) / d_total if d_total else 0

        procs = read_processes()
        elapsed = now - prev_time
        rows = []
        for pid, (name, user, state, ticks, rss) in procs.items():
            old_ticks = prev_procs.get(pid, (0, 0, 0, ticks, 0))[3]
            p_cpu = 100 * (ticks - old_ticks) / CLK_TCK / elapsed if elapsed else 0
            rows.append((pid, user, state, p_cpu, rss / 1024 / 1024, name))

        index = 3 if sort_by == "cpu" else 4
        rows.sort(key=lambda r: r[index], reverse=True)

        mem_total, mem_used = read_mem()
        load1, load5, load15 = os.getloadavg()

        # --- Малюємо ---
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        stdscr.addstr(
            0,
            0,
            f"mytop - uptime: {fmt_uptime()}  "
            f"load: {load1:.2f} {load5:.2f} {load15:.2f}"[: width - 1],
        )
        stdscr.addstr(
            1,
            0,
            f"CPU: {cpu_percent:5.1f}%   "
            f"RAM: {mem_used / 1024:.0f} / {mem_total / 1024:.0f} МБ   "
            f"Процесів: {len(procs)}"[: width - 1],
        )
        header = f"{'PID':>7} {'USER':<10} {'S':<2} {'CPU%':>6} {'MEM(МБ)':>9}  COMMAND"
        stdscr.addstr(3, 0, header[: width - 1], curses.A_REVERSE)

        for i, (pid, user, state, p_cpu, p_mem, name) in enumerate(rows):
            line_no = 4 + i
            if line_no >= height - 1:
                break
            line = f"{pid:>7} {user[:10]:<10} {state:<2} {p_cpu:>6.1f} {p_mem:>9.1f}  {name}"
            stdscr.addstr(line_no, 0, line[: width - 1])

        stdscr.addstr(
            height - 1,
            0,
            f"q - вихід | c - за CPU | m - за пам'яттю (зараз: {sort_by})"[: width - 1],
        )
        stdscr.refresh()

        prev_cpu, prev_procs, prev_time, last_draw = (total, idle), procs, now, now


if __name__ == "__main__":
    curses.wrapper(main)
