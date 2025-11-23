import os
import re
import sys
import threading
import ctypes
from functools import lru_cache
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import numpy as np
from colorama import Fore, Style
from skimage.color import rgb2lab, deltaE_cie76

try:
    import sv_ttk
except Exception:
    sv_ttk = None

try:
    import pywinstyles
except Exception:
    pywinstyles = None

# custom rust previewer
import preview_rs

TILE_DIR = "tiles"
DEFAULT_PALETTE = 32
DEFAULT_TILE_WH = (50, 50)
root = tk.Tk()
root.title("Converter")
root.geometry("920x340")
root.resizable(False, False)
if sv_ttk:
    try:
        sv_ttk.set_theme("dark")
    except Exception:
        pass

palette_count_var = tk.IntVar(value=DEFAULT_PALETTE)
selected_image_var = tk.StringVar(value="")
level_name_var = tk.StringVar(value="")
output_filename_var = tk.StringVar(value="level")


def set_dpi_aware(root):
    try:
        if sys.platform == "win32":
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.user32.SetProcessDPIAware()
        monitor_dpi = root.winfo_fpixels("1i")
        scaling_factor = max(1.0, monitor_dpi / 96.0) * 1.7
        root.tk.call("tk", "scaling", scaling_factor)
    except Exception as e:
        print(Fore.RED + f"[ERR] DPI setup failed: {e}" + Style.RESET_ALL)


def apply_theme_to_titlebar(root):
    try:
        version = sys.getwindowsversion()
        if pywinstyles and version.major == 10 and version.build >= 22000:
            pywinstyles.change_header_color(
                root,
                "#1c1c1c" if sv_ttk and sv_ttk.get_theme() == "dark" else "#fafafa",
            )
        elif pywinstyles and version.major == 10:
            pywinstyles.apply_style(
                root, "dark" if sv_ttk and sv_ttk.get_theme() == "dark" else "normal"
            )
            root.wm_attributes("-alpha", 0.99)
            root.wm_attributes("-alpha", 1)
    except Exception:
        pass


@lru_cache(maxsize=1)
def load_tiles(tile_dir=TILE_DIR):
    files = [f for f in os.listdir(tile_dir) if f.lower().endswith(".png")]

    def extract_num(s):
        m = re.findall(r"\d+", s)
        return int(m[0]) if m else 10**9

    files = sorted(files, key=extract_num)

    tile_imgs = []
    tile_ids = []
    lab_avgs = []

    for fname in files:
        path = os.path.join(tile_dir, fname)
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            print(
                Fore.RED + f"[ERR] Failed to open tile {fname}: {e}" + Style.RESET_ALL
            )
            continue
        if img.size != DEFAULT_TILE_WH:
            img = img.resize(DEFAULT_TILE_WH, Image.NEAREST)

        arr = np.array(img).astype(np.uint8)
        lab = rgb2lab(arr / 255.0)
        lab_avg = lab.mean(axis=(0, 1))
        lab_avgs.append(lab_avg)

        tile_imgs.append(img)
        tile_ids.append(extract_num(fname))
    # why did i add this? i forgor...better question what does this do??? where did i get this from??? i need to get more sleep lmao...or not ig im a 10x dev when sleep deprived
    if any(i >= 10**9 for i in tile_ids):
        tile_ids = list(range(len(tile_imgs)))

    print(Fore.GREEN + f"[!] Loaded {len(tile_imgs)} tiles (cached)." + Style.RESET_ALL)
    return tile_ids, tile_imgs, np.stack(lab_avgs) if lab_avgs else np.zeros((0, 3))


def pick_best_tile_for_rgb(rgb_tuple, tile_ids, tile_lab_avgs):
    rgb_arr = np.uint8([[rgb_tuple]])
    lab_pixel = rgb2lab(rgb_arr / 255.0)[0][0]
    if tile_lab_avgs.size == 0:
        return 0
    # delta-E :D
    # my dumbass imported delta-e then did it manually...guess i should have read THE FUCKING CODE BEFORE I BLINDLY ctrl+c ctrl+v IT HERE
    dists = deltaE_cie76(lab_pixel, tile_lab_avgs)
    best_idx = int(np.argmin(dists))
    return best_idx


def reduce_palette(img, n_colors):
    try:
        if n_colors >= 255:
            return img.convert("RGB")
        q = img.convert(
            "P", palette=Image.ADAPTIVE, colors=n_colors, dither=Image.FLOYDSTEINBERG
        )
        display_preview(q.convert("RGB"))
        return q.convert("RGB")
    except Exception as e:
        print(Fore.RED + f"[ERR] Palette reduction failed: {e}" + Style.RESET_ALL)
        return img.convert("RGB")


def convert_image_to_tile_ids(img_path, palette_colors):
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    print(
        Fore.CYAN
        + f"[+] Reducing palette to {palette_colors} colors..."
        + Style.RESET_ALL
    )
    img = reduce_palette(img, palette_colors)

    tile_ids_list, tile_imgs, tile_lab_avgs = load_tiles()
    print(Fore.CYAN + f"[+] Converting {w}x{h} Image to Tiles..." + Style.RESET_ALL)

    ids = []
    unique_cache = {}
    for y in range(h):
        for x in range(w):
            rgb = img.getpixel((x, y))
            if rgb not in unique_cache:
                best = pick_best_tile_for_rgb(rgb, tile_ids_list, tile_lab_avgs)
                unique_cache[rgb] = best
            ids.append(unique_cache[rgb])

    print(
        Fore.GREEN
        + f"[!] Mapped {len(unique_cache)} unique colors to tiles!"
        + Style.RESET_ALL
    )
    return ids, w, h


def write_mpx(path, tile_ids_flat, w, h, name):
    header = bytearray()
    header.extend(b"MPX ")
    header.extend((1).to_bytes(2, "little"))
    header.extend((1).to_bytes(2, "little"))
    header.extend(w.to_bytes(2, "little"))
    header.extend(h.to_bytes(2, "little"))
    header.extend((0x15).to_bytes(4, "little"))
    body_len = w * h + 96
    header.extend(body_len.to_bytes(4, "little"))
    info = bytearray(96)
    nm = name[:22].encode("ascii", "ignore")
    offset = 6
    NAME_FIELD_LEN = 23
    name_bytes = nm.ljust(NAME_FIELD_LEN, b" ")
    info[offset : offset + NAME_FIELD_LEN] = name_bytes

    with open(path, "wb") as f:
        f.write(header)
        f.write(bytes(tile_ids_flat))
        f.write(info)

    print(
        Fore.MAGENTA
        + f"[!] Wrote {path} ({len(header) + body_len} bytes)"
        + Style.RESET_ALL
    )


left = ttk.Labelframe(root, text="Convertor Config")
left.place(x=12, y=20, width=403, height=300)

ttk.Label(left, text="Enter Level Name:").place(x=10, y=10, width=120, height=35)
ttk.Entry(left, textvariable=level_name_var).place(x=130, y=10, width=266, height=35)

ttk.Label(left, text="Enter Level File Name:").place(x=10, y=55, width=150, height=35)
ttk.Entry(left, textvariable=output_filename_var).place(
    x=155, y=55, width=206, height=35
)
ttk.Label(left, text=".mpx").place(x=365, y=60, width=35, height=21)

ttk.Separator(left).place(x=10, y=95, width=380)
ttk.Label(left, text="Number of Colours for Palette:").place(
    x=10, y=100, width=215, height=35
)
ttk.Spinbox(left, from_=1, to=256, textvariable=palette_count_var, takefocus=0).place(
    x=210, y=100, width=185, height=35
)

select_frame = ttk.Labelframe(left, text="Select Input Image")
select_frame.place(x=10, y=140, width=380, height=85)


def select_image():
    path = filedialog.askopenfilename(
        title="Select input image",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
            ("All files", "*.*"),
        ],
    )
    if path:
        selected_image_var.set(path)
        filename_label.config(text=f"File Name: {os.path.basename(path)}")
        img = Image.open(path).convert("RGB")
        canvas_w, canvas_h = 490, 300
        img_w, img_h = img.size
        scale = min(canvas_w / img_w, canvas_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        img_small = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(img_small)
        canvas.image = tk_img
        canvas.delete("all")
        canvas.create_image(
            canvas_w // 2, canvas_h // 2, image=tk_img, anchor=tk.CENTER
        )


ttk.Button(select_frame, text="Select Image", command=select_image, takefocus=0).place(
    x=10, y=20, width=106, height=35
)
filename_label = ttk.Label(select_frame, text="File Name:", anchor="w")
filename_label.place(x=120, y=20, width=246, height=35)

ttk.Separator(left).place(x=10, y=232, width=380)
progress = ttk.Progressbar(left, mode="determinate")
progress.place(x=10, y=240, width=240, height=35)
ttk.Button(
    left, text="Start Conversion", command=lambda: start_conversion(), takefocus=0
).place(x=260, y=240, width=130, height=35)
ttk.Button(
    left, text="Quick Preview", command=lambda: start_conversion(0), takefocus=0
).place(x=279, y=149, width=110, height=35)
canvas = tk.Canvas(root, background="#18191b")
canvas.place(x=420, y=20, width=490, height=300)


def update_progress(val):
    progress["value"] = val
    root.update_idletasks()


def display_preview(preview_img):
    canvas_w, canvas_h = 490, 300
    img_w, img_h = preview_img.size
    scale = min(canvas_w / img_w, canvas_h / img_h)
    new_w = max(1, int(img_w * scale))
    new_h = max(1, int(img_h * scale))
    preview_small = preview_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    tk_img = ImageTk.PhotoImage(preview_small)
    canvas.image = tk_img
    canvas.delete("all")
    canvas.create_image(canvas_w // 2, canvas_h // 2, image=tk_img, anchor=tk.CENTER)


def worker_conversion(level: int = 1):
    try:
        if level == 0:
            generate_level = False
        else:
            generate_level = True
        update_progress(5)
        input_path = selected_image_var.get()
        if not input_path:
            messagebox.showerror("Error", "Please select an input image first!")
            update_progress(0)
            return

        palette_colors = palette_count_var.get()
        output_name = output_filename_var.get().strip() or "level"
        level_name = level_name_var.get().strip() or "Untitled Level"
        output_path = f"{output_name}.mpx"

        update_progress(16)
        tile_ids_flat, W, H = convert_image_to_tile_ids(input_path, palette_colors)

        if generate_level:
            update_progress(32)
            write_mpx(output_path, tile_ids_flat, W, H, level_name)

        update_progress(48)
        print(Fore.CYAN + "[+] Generating Preview..." + Style.RESET_ALL)
        raw_bytes = preview_rs.generate_preview(
            tile_ids_flat,
            W,
            H,
            TILE_DIR,
            [50, 50],
        )
        MAX_PREVIEW = 4000
        TILE_SIZE = min(50, max(5, MAX_PREVIEW // max(W, H)))
        preview_img = Image.frombytes(
            "RGB", (W * TILE_SIZE, H * TILE_SIZE), bytes(raw_bytes)
        )
        update_progress(64)
        print(
            Fore.YELLOW
            + f"[-] Preview generated with tile size set to {TILE_SIZE}x{TILE_SIZE}px"
            + Style.RESET_ALL
        )

        update_progress(80)
        preview_img.save("preview.png")
        print(Fore.GREEN + "[!] Preview saved as preview.png" + Style.RESET_ALL)
        display_preview(preview_img)

        if generate_level:
            update_progress(100)
            print(Fore.GREEN + "[!] Conversion Complete!" + Style.RESET_ALL)
        else:
            update_progress(100)
            print(Fore.GREEN + "[!] Preview Generated!" + Style.RESET_ALL)
    except Exception as e:
        print(
            Fore.RED
            + f"[ERR] Encountered error during conversion: {e}"
            + Style.RESET_ALL
        )
    finally:
        root.after(600, lambda: update_progress(0))


def start_conversion(level: int = 1):
    t = threading.Thread(target=worker_conversion, args=(level,), daemon=True)
    t.start()


set_dpi_aware(root)
apply_theme_to_titlebar(root)
img_part = """
██╗███╗   ███╗ ██████╗ 
██║████╗ ████║██╔════╝ 
██║██╔████╔██║██║  ███╗
██║██║╚██╔╝██║██║   ██║
██║██║ ╚═╝ ██║╚██████╔╝
╚═╝╚═╝     ╚═╝ ╚═════╝ 
"""
two_part = """
██████╗ 
╚════██╗
 █████╔╝
██╔═══╝ 
███████╗
 ╚══════╝
"""
mpx_part = """
███╗   ███╗██████╗ ██╗  ██╗
████╗ ████║██╔══██╗╚██╗██╔╝
██╔████╔██║██████╔╝ ╚███╔╝ 
██║╚██╔╝██║██╔═══╝  ██╔██╗ 
██║ ╚═╝ ██║██║     ██╔╝ ██╗
╚═╝     ╚═╝╚═╝     ╚═╝  ╚═╝
"""
lines_img = img_part.strip().split("\n")
lines_two = two_part.strip().split("\n")
lines_mpx = mpx_part.strip().split("\n")
for i in range(len(lines_img)):
    print(
        Fore.CYAN
        + lines_img[i]
        + Fore.WHITE
        + lines_two[i]
        + Fore.GREEN
        + lines_mpx[i]
        + Style.RESET_ALL
    )
print(f"[i] A tool made by {Fore.BLUE + 'EndoBotM' + Style.RESET_ALL} <3")
if __name__ == "__main__":
    root.mainloop()
