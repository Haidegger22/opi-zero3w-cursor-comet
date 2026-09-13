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

