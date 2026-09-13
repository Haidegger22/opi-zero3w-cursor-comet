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
