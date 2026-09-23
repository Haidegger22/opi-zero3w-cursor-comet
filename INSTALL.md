# Установка курсора-кометы — по шагам (copy-paste)

Инструкция для Debian 13 + MATE (X11). Каждый блок можно вставить в терминал целиком.

## Шаг 1. Зависимости

```bash
sudo apt update && sudo apt install -y python3-gi python3-gi-cairo python3-xlib gir1.2-gtk-3.0 git
```

## Шаг 2. Скачать репозиторий

```bash
cd ~ && git clone https://github.com/Haidegger22/opi-zero3w-cursor-comet.git cursor-src
```

## Шаг 3. Установить скрипты

```bash
mkdir -p ~/.local/bin
cp ~/cursor-src/cursor-comet.py ~/.local/bin/
chmod +x ~/.local/bin/cursor-comet.py
cp ~/cursor-src/make_empty_cursor.py ~/
```

## Шаг 4. Создать невидимую тему курсора

```bash
python3 ~/make_empty_cursor.py
```

## Шаг 5. Автозапуск (с подстановкой твоего домашнего пути)

```bash
mkdir -p ~/.config/autostart
sed "s|/home/orangepi|$HOME|g" ~/cursor-src/autostart/cursor-comet.desktop > ~/.config/autostart/cursor-comet.desktop
```

## Шаг 6. Запустить сейчас

```bash
DISPLAY=:0 nohup ~/.local/bin/cursor-comet.py --hide-cursor > ~/comet.log 2>&1 &
```

## Шаг 7. Проверка

Курсор должен стать **чёрным ядром с зелёным ореолом** и хвостом. Системной стрелки быть не должно.
Если что-то не так — смотри лог: `tail -20 ~/comet.log`

## Важно

- Требуется **X11** (не Wayland) и WM/DE, работающий с настройкой `cursor-theme` (проверено на MATE).
- Папку `~/.icons/comet-hidden` **не удаляй** — это и есть невидимый курсор.
- Скрипт сам следит за темой: если её сбросят (смена оформления), вернёт в течение 5 секунд.

## Откат

```bash
pkill -f cursor-comet.py
gsettings set org.mate.peripherals-mouse cursor-theme mate
xsetroot -cursor_name left_ptr
```


## Игровой курсор: установка

Ставится поверх кометы. Нужен, только если на машине играют в игры, которые ведут
**свой** курсор (Hedgewars и подобные).

### Шаг 8. Установить три скрипта

```bash
mkdir -p ~/.local/bin
cp game-cursor.py joy-to-keys.py game-pointer.py ~/.local/bin/
chmod +x ~/.local/bin/game-cursor.py ~/.local/bin/joy-to-keys.py ~/.local/bin/game-pointer.py
```

### Шаг 9. Служба сторожа с автоперезапуском

```bash
mkdir -p ~/.config/systemd/user
cp game-cursor.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now game-cursor
systemctl --user status game-cursor --no-pager | head -5
```

Ярлык автозапуска для сторожа создавать **не нужно**: иначе после входа в сессию
запустятся два сторожа и начнут спорить друг с другом.

### Шаг 10. Проверка

```bash
tail -5 /tmp/game-cursor.log            # сторож видит игру и переключает режимы
pgrep -af joy-to-keys.py                # в матче должен работать мост
pgrep -af cursor-comet.py               # на рабочем столе — комета
```

Полезно знать: если мост остановить ровно между нажатием и отпусканием, клавиша
останется «зажатой» в X, и система начнёт повторять её сама — в приложении это
выглядит как бесконечная прокрутка. Оба скрипта (сторож и мост) при завершении
отпускают свои клавиши сами; если клавиша всё же залипла, её снимают инструментом
`tools/stuck-keys.py` из репозитория `opi-zero3w-m5hub`.


## Полный код файлов (установка без git)

### 1. cursor-comet.py

```bash
mkdir -p $(dirname $HOME/.local/bin/cursor-comet.py)
cat > $HOME/.local/bin/cursor-comet.py << 'SCRIPT_EOF'
#!/usr/bin/env python3
# Курсор-«комета»: своя отрисовка курсора. Компактное окно 96x96,
# следует за указателем (меньше перерисовок → нет мерцания на llvmpipe).
# Запуск: cursor-comet.py [--hide-cursor]
import os, sys, math, time, signal, subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo
from Xlib import display, X
from Xlib.ext import xfixes
import atexit

HIDE = "--hide-cursor" in sys.argv
THEME_FILE = "/tmp/comet_prev_cursor_theme"
W = H = 96            # размер окна
CORE_R = 5.0          # радиус чёрного ядра
HALO_R = 17.0         # радиус ореола
NEON = (0.55, 1.00, 0.60)
TTL = 0.45            # жизнь точки хвоста (с)
TRAIL_MAX = 24


def screen_size():
    d = display.Display()
    s = d.screen()
    return s.width_in_pixels, s.height_in_pixels


class Comet(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.sw, self.sh = screen_size()
        self.dpy = display.Display()
        self.root = self.dpy.screen().root
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        scr = self.get_screen()
        vis = scr.get_rgba_visual()
        if vis:
            self.set_visual(vis)
        self.set_size_request(W, H)
        self.resize(W, H)
        self.trail = []          # [(x, y, t)] в экранных координатах
        self._win_pos = (None, None)
        self._hide_t = 0.0
        self._raise_t = 0.0      # время последнего подъёма над панелью
        self._theme_t = 0.0      # время последней проверки темы курсора
        self.connect("draw", self.on_draw)
        self.connect("realize", self.on_realize)
        self.connect("map-event", self.on_map)
        self.show_all()
        GLib.timeout_add(16, self.tick)

    def on_realize(self, *_):
        try:
            self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass
        # override-redirect: WM не управляет окном — панель не опустит курсор
        try:
            self.get_window().set_override_redirect(True)
        except Exception:
            pass

    def on_map(self, *_):
        try:
            self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass
        return False

    def _hide_everywhere(self):
        try:
            self.root.xfixes_hide_cursor()
            for w in self.root.query_tree().children:
                try:
                    w.xfixes_hide_cursor()
                except Exception:
                    pass
        except Exception:
            pass

    def _ensure_theme(self):
        """Восстанавливает невидимую тему, если её сбросили (смена оформления)."""
        try:
            out = subprocess.run(["gsettings", "get", "org.mate.peripherals-mouse",
                                  "cursor-theme"], capture_output=True, text=True,
                                 timeout=5).stdout
            if "comet-hidden" not in out:
                for key in ("org.mate.peripherals-mouse", "org.gnome.desktop.interface"):
                    subprocess.run(["gsettings", "set", key, "cursor-theme",
                                    "comet-hidden"], check=False)
                subprocess.run(["xsetroot", "-cursor", "/tmp/comet_empty.xbm",
                                "/tmp/comet_empty.xbm"], check=False)
                print("[comet] тему сбросили — восстановил", flush=True)
        except Exception:
            pass
        return True

    def tick(self):
        try:
            p = self.root.query_pointer()
            x, y = p.root_x, p.root_y
        except Exception:
            return True
        now = time.time()
        if HIDE and now - self._hide_t > 0.2:
            self._hide_t = now
            self._hide_everywhere()
        if HIDE and now - self._theme_t > 5.0:
            self._theme_t = now
            self._ensure_theme()
        # периодически поднимаем окно: иначе панель MATE (тоже DOCK) накрывает комету
        if now - self._raise_t > 0.3:
            self._raise_t = now
            try:
                self.get_window().raise_()
            except Exception:
                pass
        if not self.trail or self.trail[-1][:2] != (x, y):
            self.trail.append((x, y, now))
        self.trail = [t for t in self.trail if now - t[2] < TTL][-TRAIL_MAX:]
        # двигаем окно так, чтобы курсор был в центре
        wx, wy = x - W // 2, y - H // 2
        if (wx, wy) != self._win_pos:
            self._win_pos = (wx, wy)
            self.move(wx, wy)
            self.queue_draw()
        elif self.trail:
            self.queue_draw()
        return True

    def on_draw(self, w, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        wx, wy = self._win_pos
        if wx is None:
            return False
        cx, cy = W / 2.0, H / 2.0
        now = time.time()
        # хвост
        for tx, ty, tt in reversed(self.trail[:-1]):
            f = (now - tt) / TTL
            if f >= 1.0:
                continue
            r = CORE_R * (1.0 - f) * 0.9 + 1.0
            cr.set_source_rgba(NEON[0], NEON[1], NEON[2], 0.45 * (1.0 - f) ** 1.5)
            cr.arc(tx - wx, ty - wy, r, 0, 2 * math.pi)
            cr.fill()
        # ореол
        halo = cairo.RadialGradient(cx, cy, CORE_R * 0.4, cx, cy, HALO_R)
        halo.add_color_stop_rgba(0.0, NEON[0], NEON[1], NEON[2], 0.55)
        halo.add_color_stop_rgba(0.45, NEON[0], NEON[1], NEON[2], 0.18)
        halo.add_color_stop_rgba(1.0, NEON[0], NEON[1], NEON[2], 0.0)
        cr.set_source(halo)
        cr.arc(cx, cy, HALO_R, 0, 2 * math.pi)
        cr.fill()
        # ядро
        cr.set_source_rgba(0.03, 0.04, 0.05, 0.95)
        cr.arc(cx, cy, CORE_R, 0, 2 * math.pi)
        cr.fill()
        return False


def main():
    prev_theme = None
    if HIDE:
        xfixes.hide_cursor(display.Display().screen().root)
        try:
            old = subprocess.run(["gsettings", "get", "org.mate.peripherals-mouse",
                                  "cursor-theme"], capture_output=True, text=True).stdout.strip()
            prev_theme = old.strip("'") or "mate"
            with open(THEME_FILE, "w") as f:
                f.write(prev_theme)
            subprocess.run(["gsettings", "set", "org.mate.peripherals-mouse",
                            "cursor-theme", "comet-hidden"])
            subprocess.run(["gsettings", "set", "org.gnome.desktop.interface",
                            "cursor-theme", "comet-hidden"], check=False)
            print(f"[comet] тема курсора -> comet-hidden (прежняя: {prev_theme})", flush=True)
        except Exception as e:
            print("[comet] тема не применена:", e, flush=True)
        # пустой root-курсор (стрелка на рабочем столе)
        try:
            xbm = "/tmp/comet_empty.xbm"
            with open(xbm, "w") as f:
                f.write("#define e_width 16\n#define e_height 16\nstatic char e_bits[] = {\n")
                f.write(",".join(["0x00"] * 32))
                f.write("\n};\n")
            subprocess.run(["xsetroot", "-cursor", xbm, xbm], check=False)
            print("[comet] root-курсор -> пустой", flush=True)
        except Exception as e:
            print("[comet] root-курсор:", e, flush=True)

    def bye(*_a):
        if HIDE:
            try:
                old = prev_theme
                if not old and os.path.exists(THEME_FILE):
                    old = open(THEME_FILE).read().strip()
                if old:
                    subprocess.run(["gsettings", "set", "org.mate.peripherals-mouse",
                                    "cursor-theme", old])
                subprocess.run(["xsetroot", "-cursor_name", "left_ptr"], check=False)
                print(f"[comet] курсор восстановлен ({old})", flush=True)
            except Exception:
                pass
        Gtk.main_quit()

    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    atexit.register(lambda: None)
    c = Comet()
    print("[comet] запущена", flush=True)
    Gtk.main()


if __name__ == "__main__":
    main()
SCRIPT_EOF
chmod +x $HOME/.local/bin/cursor-comet.py 2>/dev/null || true
```

### 2. make_empty_cursor.py

```bash
mkdir -p $(dirname $HOME/make_empty_cursor.py)
cat > $HOME/make_empty_cursor.py << 'SCRIPT_EOF'
import os, shutil, struct
SIZES = [16, 24, 32, 48]
HOME = os.path.expanduser("~")
def img(size):
    hdr = struct.pack("<IIIII", 36, 0xfffd0002, size, 1, size)
    hdr += struct.pack("<IIII", size, 0, 0, 1)
    return hdr + b"\x00" * (size * size * 4)
def xcursor():
    n = len(SIZES)
    toc = []
    pos = 16 + 12 * n
    chunks = []
    for s in SIZES:
        c = img(s)
        toc.append(struct.pack("<III", 0xfffd0002, s, pos))
        chunks.append(c)
        pos += len(c)
    return struct.pack("<4sIII", b"Xcur", 16, 0x00010000, n) + b"".join(toc) + b"".join(chunks)
import glob
src = "/usr/share/icons/mate/cursors"
if not os.path.isdir(src):
    src = (glob.glob("/usr/share/icons/*/cursors") or ["/usr/share/icons"])[0]
names = sorted(os.listdir(src)) or ["default", "left_ptr"]
for theme in (".icons/comet-hidden", ".local/share/icons/comet-hidden"):
    d = os.path.join(HOME, theme, "cursors")
    shutil.rmtree(os.path.join(HOME, theme), ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    data = xcursor()
    with open(os.path.join(d, "base"), "wb") as f:
        f.write(data)
    for n in names:
        p = os.path.join(d, n)
        if not os.path.exists(p):
            os.symlink("base", p)
    print(theme, "->", len(names), "курсоров, файл", len(data), "байт")
SCRIPT_EOF
chmod +x $HOME/make_empty_cursor.py 2>/dev/null || true
```

### 3. cursor-comet.desktop

```bash
mkdir -p $(dirname $HOME/.config/autostart/cursor-comet.desktop)
cat > $HOME/.config/autostart/cursor-comet.desktop << 'SCRIPT_EOF'
[Desktop Entry]
Type=Application
Name=Курсор-комета
Comment=Своя отрисовка курсора (неоновая комета) + скрытие системного курсора
Exec=/home/orangepi/.local/bin/cursor-comet.py --hide-cursor
X-GNOME-Autostart-enabled=true
Terminal=false
SCRIPT_EOF
chmod +x $HOME/.config/autostart/cursor-comet.desktop 2>/dev/null || true
```

### 4. game-cursor.py

```python
#!/usr/bin/env python3
"""game-cursor.py — курсор для игр на Zero 3W.

Рабочий стол рисует курсор «кометой» (cursor-comet.py): у неё шлейф, и диск кометы
уходит в сторону от настоящей точки указателя. В игре это мешает — например в меню
выбора оружия непонятно, куда именно попадёт клик.

Поведение:
  • на экране окно игры -> комета останавливается, включается game-pointer.py
    (точный прицел ровно в точке указателя, клики проходят сквозь него);
  • игр на экране нет   -> прицел выключается, комета возвращается как была.

Скрипт кометы не изменяется: сторож только запускает и останавливает процессы.

Запуск: game-cursor.py
Лог:    /tmp/game-cursor.log
"""
import os
import subprocess
import sys
import time

from Xlib import X, XK, display, protocol
from Xlib.ext import xtest

CURSOR_KEYS = ("KP_4", "KP_6", "KP_8", "KP_2")   # клавиши игрового курсора (мост)

COMET = "/home/orangepi/.local/bin/cursor-comet.py"
COMET_ARGS = ["--hide-cursor"]
POINTER = "/home/orangepi/.local/bin/game-pointer.py"
BRIDGE = "/home/orangepi/.local/bin/joy-to-keys.py"
GAMES = {"hedgewars", "hwengine", "warmux", "wormux", "retroarch", "supertux2", "0ad"}
POLL = 1.0          # период опроса, секунды
GRACE = 1           # секунд устойчивости перед переключением
LOG = "/tmp/game-cursor.log"


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


RECENTER_FLAG = "/tmp/m5hub-recenter"   # разрешение m5hub переносить указатель в центр
_recenter_flag = None                   # что выставлено сейчас (чтобы не дёргать диск зря)


def sync_recenter_flag(need):
    """Разрешить m5hub переносить указатель в центр экрана у края.

    Перенос нужен только в матче: там курсор ведёт сама игра, а игровой мост
    читает прыжки указателя — без переноса движение «упирается в стенку». На
    рабочем столе и в меню перенос виден как прыжок курсора в центр, поэтому там
    он запрещён. m5hub проверяет наличие этого файла в цикле движения.
    """
    global _recenter_flag
    if _recenter_flag == need:
        return
    try:
        if need:
            with open(RECENTER_FLAG, "w") as f:
                f.write("%d\n" % os.getpid())
        else:
            if os.path.exists(RECENTER_FLAG):
                os.remove(RECENTER_FLAG)
        _recenter_flag = need
        log("перенос указателя у края: %s" % ("разрешён (матч)" if need else "запрещён"))
    except Exception as e:
        log("пометку переноса не удалось переключить: %r" % (e,))


def walk(w, depth=0):
    """Обходим дерево окон: оконный менеджер заворачивает окно игры в рамку,
    поэтому класс игры виден только в глубине дерева."""
    yield w
    if depth >= 3:
        return
    try:
        for c in w.query_tree().children:
            yield from walk(c, depth + 1)
    except Exception:
        return


def game_windows(d):
    """Список окон игр, которые сейчас реально видны на экране."""
    out = []
    try:
        top = d.screen().root.query_tree().children
    except Exception:
        return out
    for t in top:
        for w in walk(t):
            try:
                at = w.get_attributes()
                if at.map_state != X.IsViewable:
                    continue
                cls = w.get_wm_class() or ()
                names = {str(c).lower() for c in cls}
                if names & GAMES:
                    geo = w.get_geometry()
                    # игровым считаем только окно, занимающее заметную часть экрана
                    if geo.width > 400 and geo.height > 300:
                        out.append((w.id, tuple(cls), geo.width, geo.height))
            except Exception:
                continue
    return out


def ensure_fullscreen(d, win_id, env):
    """Окно игры должно занимать весь экран.

    Двумя шагами: (1) просим у оконного менеджера настоящий полный экран;
    (2) проверяем факт — если окно всё равно стоит со сдвигом на рамку
    (заголовок съедает ~35 px снизу), сдвигаем его в угол экрана. Иначе нижняя
    полоса с кнопками уходит за край.
    """
    try:
        root = d.screen().root
        wm_state = d.intern_atom("_NET_WM_STATE")
        fs = d.intern_atom("_NET_WM_STATE_FULLSCREEN")
        win = d.create_resource_object("window", win_id)
        ev = protocol.event.ClientMessage(window=win, client_type=wm_state,
                                          data=(32, [1, fs, 0, 1, 0]))
        root.send_event(ev,
                        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.flush()
    except Exception as e:
        log("полный экран не удался: %r" % (e,))

    try:
        res = subprocess.run(["xdotool", "getwindowgeometry", str(win_id)],
                             capture_output=True, text=True, env=env)
        pos = ""
        for line in res.stdout.splitlines():
            if "Position:" in line:
                pos = line.split("Position:")[1].strip().split()[0]
        if pos and pos != "0,0":
            subprocess.run(["xdotool", "windowmove", str(win_id), "0", "0"],
                           capture_output=True, env=env)
            log("окно %s сдвинуто в угол экрана (было %s)" % (win_id, pos))
    except Exception as e:
        log("сдвиг окна не удался: %r" % (e,))


def pids_of(pattern):
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def kill_by_pattern(pattern):
    for p in pids_of(pattern):
        subprocess.run(["kill", str(p)], capture_output=True)


def start_pointer(env):
    if pids_of(POINTER):
        return
    subprocess.Popen([sys.executable, POINTER], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, env=env)
    log("включён точный курсор игры")


def stop_pointer():
    kill_by_pattern(POINTER)
    log("точный курсор игры выключен")


def start_comet(env):
    if pids_of(COMET):
        return
    subprocess.Popen([sys.executable, COMET] + COMET_ARGS,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, env=env)
    log("комета возвращена (рабочий стол)")


def start_bridge(env):
    """В матче: игра ведёт свой курсор, движения указателя она не видит, но клавиши
    перемещения курсора принимает — поэтому переводим движение джойстика в клавиши."""
    if pids_of(BRIDGE):
        return
    subprocess.Popen([sys.executable, BRIDGE],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, env=env)
    log("включён мост «джойстик → клавиши курсора»")


def release_cursor_keys():
    """Отпустить клавиши игрового курсора после остановки моста.

    Если мост убит ровно между нажатием и отпусканием, клавиша остаётся
    «зажатой» в X: сервер повторяет её сам ~30 раз в секунду, и в приложении это
    выглядит как бесконечная прокрутка (поймано 24.09.2026 — зажатый KP_Down).
    Снимается только явным KeyRelease, перезапуск драйвера не помогает.
    """
    try:
        d = display.Display()
        for name in CURSOR_KEYS:
            code = d.keysym_to_keycode(XK.string_to_keysym(name))
            if code:
                xtest.fake_input(d, X.KeyRelease, code)
        d.sync()
    except Exception as e:
        log("клавиши курсора не отпустились: %r" % (e,))


def stop_bridge():
    kill_by_pattern(BRIDGE)
    time.sleep(0.2)     # дать процессу уйти, чтобы отпускание не спорило с его нажатием
    release_cursor_keys()


def is_engine_window(wins):
    """Матч (движок hwengine) или фронтенд (меню, hedgewars)."""
    for _wid, cls, _w, _h in wins:
        if {str(c).lower() for c in cls} & {"hwengine"}:
            return True
    return False


def main():
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    d = display.Display()
    mode = "none"          # none | frontend (меню игры) | engine (матч)
    pending_mode = None
    pending_since = None
    tick_n = 0
    log("старт: слежу за играми " + ", ".join(sorted(GAMES)))

    while True:
        try:
            wins = game_windows(d)
            engine = is_engine_window(wins)
            want_mode = "engine" if engine else ("frontend" if wins else "none")

            if want_mode != mode:
                # режим хочет измениться — ждём GRACE секунд устойчивости
                if pending_mode != want_mode:
                    pending_mode = want_mode
                    pending_since = time.time()
                elif time.time() - pending_since >= GRACE:
                    if want_mode == "engine":
                        # ИДЁТ МАТЧ: игра ведёт свой курсор и не видит движение указателя,
                        # сделанное виртуально. Комету и оверлей убираем, движение
                        # джойстика переводим в клавиши игрового курсора.
                        kill_by_pattern(COMET)
                        stop_pointer()
                        start_bridge(env)
                        log("МАТЧ %s — курсор игры + мост клавиш" % (wins[0][1],))
                    elif want_mode == "frontend":
                        # МЕНЮ игры: мышь и джойстик тут работают сами, а оверлей-прицел
                        # только мешал — оставляем комету, как было раньше.
                        stop_bridge()
                        stop_pointer()
                        start_comet(env)
                        for wid, cls, gw, gh in wins:
                            ensure_fullscreen(d, wid, env)
                        log("МЕНЮ игры %s — комета, мост выключен" % (wins[0][1],))
                    else:
                        stop_bridge()
                        stop_pointer()
                        start_comet(env)
                        log("рабочий стол — комета вернулась")
                    mode = want_mode
                    pending_mode = None
            else:
                pending_mode = None
                # присмотр: если нужный компонент умер — поднимаем его заново
                if mode == "engine":
                    if not pids_of(BRIDGE):
                        log("мост пропал — поднимаю заново")
                        start_bridge(env)
                    if pids_of(COMET):
                        kill_by_pattern(COMET)
                    if pids_of(POINTER):
                        stop_pointer()
                    if tick_n % 5 == 0:      # раз в ~5 с подтверждаем полный экран
                        for wid, cls, gw, gh in wins:
                            ensure_fullscreen(d, wid, env)
                elif mode == "frontend":
                    if not pids_of(COMET):
                        log("комета пропала — поднимаю заново")
                        start_comet(env)
                    if pids_of(BRIDGE):
                        stop_bridge()
                    if pids_of(POINTER):
                        stop_pointer()
                else:
                    if not pids_of(COMET):
                        log("комета пропала — поднимаю заново")
                        start_comet(env)
                    if pids_of(BRIDGE):
                        stop_bridge()
                    if pids_of(POINTER):
                        stop_pointer()
                tick_n += 1
            # перенос указателя у края разрешаем только в матче
            sync_recenter_flag(mode == "engine")
        except Exception as e:
            log("ошибка: %r" % (e,))
        time.sleep(POLL)


def _cleanup_flag(*_):
    """Снять пометку переноса: с ней m5hub переносит указатель в центр и на столе."""
    try:
        if os.path.exists(RECENTER_FLAG):
            os.remove(RECENTER_FLAG)
    except Exception:
        pass


if __name__ == "__main__":
    import signal
    for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(_sig, lambda *_: (_cleanup_flag(), os._exit(0)))
        except Exception:
            pass
    try:
        main()
    finally:
        _cleanup_flag()
```

### 5. joy-to-keys.py

```
#!/usr/bin/env python3
"""joy-to-keys.py — мост «джойстик → игровой курсор» для Hedgewars.

Почему так: игра ведёт собственный курсор и НЕ видит движение указателя, сделанное
виртуально (XWarpPointer / XTEST) — проверено кадрами. Но клавиши перемещения
игрового курсора (цифровой блок: 4/6/8/2) игра принимает, даже будучи нажатыми
виртуально — это и есть обход.

Логика (версия, которую Артём принял как «отлично работает», с чуть меньшей скоростью):
  • копим смещения указателя; как только накопилось THRESHOLD пикселей — нажимаем
    клавишу направления. Так ловится и медленное движение (мелкие шаги джойстика);
  • сколько пикселей приходится на одно нажатие — задаёт скорость: STEP_PX
    (больше = медленнее). По горизонтали курсор игры ходит быстрее, поэтому там
    нажатий вдвое меньше;
  • если движение идёт ровно, без пауз (так двигает мышь) — клавиши не жмём:
    мышь игра видит сама, иначе курсор двигался бы вдвое;
  • если движения не было 0.35 с — накопитель сбрасываем, чтобы остаток не сработал
    позже, «догоняя» курсор.

Запуск: joy-to-keys.py
Лог:    /tmp/joy-to-keys.log
"""
import math
import os
import queue
import signal
import threading
import time

from Xlib import X, XK, display
from Xlib.ext import xtest

JUMP_MIN = 3         # шаг указателя меньше этого — дрожание стика, игнорируем
SCALE = 14           # пикселей пути на одно нажатие по вертикали (больше = медленнее)
POLL = 0.006         # ~160 опросов в секунду
KEY_HOLD = 0.030     # держим клавишу 30 мс, иначе игра не успевает её принять
KEY_GAP = 0.004
MAX_PRESS = 3        # не больше нажатий на один шаг указателя
RESET_PX = 100       # прыжок больше этого = служебный перенос указателя
                     # (m5hub уводит его в центр, когда упёрся в край экрана):
                     # это не движение стика, клавиши жать нельзя
LOG = "/tmp/joy-to-keys.log"

KEYS = {"right": "KP_6", "left": "KP_4", "up": "KP_8", "down": "KP_2"}


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def release_keys():
    """Отпустить все клавиши курсора — на случай выхода посреди нажатия.

    Зачем: если процесс убьют ровно между нажатием и отпусканием (сторож гасит
    мост, игра закрывается, systemctl restart), отпускание не уйдёт, и X-сервер
    будет считать клавишу удержанной и повторять её сам ~30 раз в секунду — в
    приложении это выглядит как бесконечная прокрутка. Поймано на практике
    24.09.2026 (зажатый KP_Down); снимается только явным KeyRelease.
    """
    try:
        own = display.Display()
        for name in KEYS:
            code = own.keysym_to_keycode(XK.string_to_keysym(KEYS[name]))
            if code:
                xtest.fake_input(own, X.KeyRelease, code)
        own.sync()
    except Exception:
        pass


def main():
    d = display.Display()
    root = d.screen().root
    codes = {name: d.keysym_to_keycode(XK.string_to_keysym(sym)) for name, sym in KEYS.items()}

    # выход по сигналу: сначала отпустить клавиши, потом уходить
    def bye(*_):
        release_keys()
        log("выход: клавиши курсора отпущены")
        os._exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, bye)
        except Exception:
            pass

    def press(dpy, name):
        """Одно короткое нажатие клавиши перемещения игрового курсора."""
        code = dpy.keysym_to_keycode(XK.string_to_keysym(KEYS[name]))
        xtest.fake_input(dpy, X.KeyPress, code)
        dpy.flush()
        time.sleep(KEY_HOLD)
        xtest.fake_input(dpy, X.KeyRelease, code)
        dpy.flush()
        time.sleep(KEY_GAP)

    # нажатия делаем в отдельном потоке: иначе цикл наблюдения за указателем
    # «застревал» на 30 мс на каждое нажатие, прыжки копились — и курсор залипал
    press_q = queue.Queue(maxsize=8)

    def presser():
        # у потока своё подключение к X: Xlib не потокобезопасен
        own = display.Display()
        while True:
            name = press_q.get()
            try:
                press(own, name)
            except Exception:
                try:
                    own = display.Display()
                except Exception:
                    pass

    threading.Thread(target=presser, daemon=True).start()

    log("старт: дрожание < %d px игнор, %d px на одно нажатие (больше = медленнее)"
        % (JUMP_MIN, SCALE))

    prev = root.query_pointer()
    prev_x, prev_y = prev.root_x, prev.root_y
    presses = {"right": 0, "left": 0, "up": 0, "down": 0}
    window = []                   # для отличения мыши: у неё движение без пауз

    while True:
        try:
            p = root.query_pointer()
            x, y = p.root_x, p.root_y
            dx, dy = x - prev_x, y - prev_y
            prev_x, prev_y = x, y

            dist = math.hypot(dx, dy)
            if dist >= RESET_PX:
                # Служебный перенос указателя (m5hub уводит его в центр, когда
                # упирается в край экрана). Это не движение стика: клавиши не жмём,
                # иначе курсор игры прыгнет. Накопитель сбрасываем, чтобы остаток
                # не сработал позже.
                window.clear()
                continue
            window.append(dist >= JUMP_MIN)
            if len(window) > 12:
                window.pop(0)

            if dist >= JUMP_MIN:
                # джойстик двигает указатель редкими крупными прыжками (по данным журнала:
                # раз в ~70 мс, шаги 14–33 px), между ними — дрожание 0–2 px. Поэтому:
                # реагируем на каждый прыжок, дрожание игнорируем, ничего не накапливаем.
                smooth = len(window) >= 8 and all(window)
                if not smooth:
                    # ровное движение без пауз = мышь: игра видит её сама, клавиши не нужны
                    n = max(1, min(MAX_PRESS, int(round(dist / SCALE))))
                    plan = []
                    if abs(dx) >= JUMP_MIN:
                        plan.append(("right" if dx > 0 else "left", n))
                    if abs(dy) >= JUMP_MIN:
                        plan.append(("down" if dy > 0 else "up", n))
                    for name, count in plan:
                        for _ in range(count):
                            try:
                                press_q.put_nowait(name)
                            except queue.Full:
                                pass          # очередь полна — лишнее просто пропускаем
                        presses[name] += count
                    total = sum(presses.values())
                    if total <= 40 or total % 25 == 0:
                        log("шаг %+.0f,%+.0f (%.0f px) -> %s | всего R%d L%d U%d D%d"
                            % (dx, dy, dist, ", ".join("%s×%d" % kv for kv in plan),
                               presses["right"], presses["left"], presses["up"], presses["down"]))
        except Exception as e:
            log("ошибка: %r" % (e,))
        time.sleep(POLL)


if __name__ == "__main__":
    main()
```

### 6. game-pointer.py

```
#!/usr/bin/env python3
"""game-pointer.py — точный курсор для игр (Zero 3W).

Зачем: на рабочем столе курсор рисует «комета» (cursor-comet.py) — у неё есть шлейф,
а шлейф визуально отстаёт от указателя. В игре это мешает: непонятно, куда именно
попадёт клик (например в меню выбора оружия).

Что делает этот скрипт: рисует аккуратный прицел-перекрестие РОВНО в точке указателя,
без шлейфа и без сглаживания, 60 раз в секунду. Окно прозрачно для кликов
(пустая область ввода), поэтому нажатия уходят прямо в игру.

Запуск: game-pointer.py          (живёт, пока его не остановят)
"""
import math
import os
import sys
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

SIZE = 44          # размер окна курсора
TICK_MS = 16       # ~60 кадров в секунду
LOG = "/tmp/game-pointer.log"


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


class Pointer(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_size_request(SIZE, SIZE)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.connect("draw", self.on_draw)
        self.connect("realize", self.on_realize)
        self.connect("map-event", self.on_map)
        self.show_all()
        self.dpy = Gdk.Display.get_default()
        self.last = None
        GLib.timeout_add(TICK_MS, self.tick)

    def on_realize(self, *_):
        self._apply_input()
        try:
            self.get_window().set_override_redirect(True)
        except Exception:
            pass

    def on_map(self, *_):
        # GTK сбрасывает форму ввода при показе окна — применяем ещё раз
        self._apply_input()
        return False

    def _apply_input(self):
        """Пустая область ввода: клики не задерживаются оверлеем, а уходят в игру."""
        try:
            self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass

    def pointer(self):
        """Положение указателя на экране (GTK отдаёт: экран, X, Y)."""
        seat = self.dpy.get_default_seat()
        _screen, x, y = seat.get_pointer().get_position()
        return x, y

    def tick(self):
        try:
            x, y = self.pointer()
            if (x, y) != self.last:
                self.last = (x, y)
                self.move(x - 6, y - 6)   # чуть влево-вверх, чтобы точка была в центре прицела
            self._n = getattr(self, "_n", 0) + 1
            if self._n % 30 == 0:          # ~2 раза в секунду подстраховываемся
                self._apply_input()
        except Exception as e:
            log("ошибка: %r" % (e,))
        return True

    def on_draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        c = SIZE / 2.0
        # крестик: чёрная подложка + белые штрихи (видно на любом фоне)
        for width, color in ((5.0, (0, 0, 0, 0.85)), (2.4, (1, 1, 1, 1))):
            cr.set_line_width(width)
            cr.set_source_rgba(*color)
            r1, r2 = 6.0, 16.0
            for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                cr.move_to(c + math.cos(a) * r1, c + math.sin(a) * r1)
                cr.line_to(c + math.cos(a) * r2, c + math.sin(a) * r2)
            cr.stroke()
        # точка точно в позиции указателя
        for rad, color in ((3.4, (0, 0, 0, 0.9)), (1.8, (1, 0.25, 0.15, 1))):
            cr.set_source_rgba(*color)
            cr.arc(c, c, rad, 0, 2 * math.pi)
            cr.fill()
        return False


def main():
    log("старт точного курсора для игр")
    win = Pointer()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
```

### 7. game-cursor.service

```ini
[Unit]
Description=Курсор для игр (Hedgewars): комета в меню и на рабочем столе, мост клавиш в матче
Documentation=file:/home/orangepi/.hermes/skills/devops/x11-cursor-and-overlay-control/SKILL.md
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/orangepi/.Xauthority
ExecStart=/usr/bin/python3 /home/orangepi/.local/bin/game-cursor.py
# сторож следит за играми каждую секунду и сам поднимает комету/мост;
# если он упадёт — служба поднимет его заново
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```
