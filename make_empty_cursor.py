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
