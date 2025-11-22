import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import numpy as np
from colorama import Fore, Style
import re
from tkinter import filedialog
from PIL import Image, ImageTk
import sv_ttk
import sys
import pywinstyles
import ctypes

root = tk.Tk()
root.title("Converter")
root.geometry("920x340")
root.resizable(False, False)
sv_ttk.set_theme("dark")
palette_count_var = tk.IntVar(value=32)
selected_image_var = tk.StringVar(value="File Name:")
level_name_var = tk.StringVar(value="")
output_filename_var = tk.StringVar(value="level")
TILE_DIR = "tiles"
PALETTE_COLORS = 32
INPUT_IMAGE = ""
LEVEL_NAME = ""
OUTPUT_MPX = ""


def apply_theme_to_titlebar(root):
    version = sys.getwindowsversion()

    if version.major == 10 and version.build >= 22000:
        pywinstyles.change_header_color(
            root, "#1c1c1c" if sv_ttk.get_theme() == "dark" else "#fafafa"
        )
    elif version.major == 10:
        pywinstyles.apply_style(
            root, "dark" if sv_ttk.get_theme() == "dark" else "normal"
        )
        root.wm_attributes("-alpha", 0.99)
        root.wm_attributes("-alpha", 1)


def select_image():
    path = filedialog.askopenfilename(
        title="Select input image",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
            ("All files", "*.*"),
        ],
    )
    # WHY IS IT SO FUCKING BIG ITS JUST TO GET A VARIABLE AND TO DISPLAY THE IMAGE
    if path:
        selected_image_var.set(path)
        filename_label.config(text=f"File Name: {os.path.basename(path)}")
        img = Image.open(path)
        canvas_w = 490
        canvas_h = 300
        img_w, img_h = img.size
        scale = min(canvas_w / img_w, canvas_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        canvas.image = tk_img
        canvas.delete("all")
        canvas.create_image(
            canvas_w // 2, canvas_h // 2, image=tk_img, anchor=tk.CENTER
        )


def avg_rgb(img):
    arr = np.array(img)
    r = int(arr[:, :, 0].mean())
    g = int(arr[:, :, 1].mean())
    b = int(arr[:, :, 2].mean())
    return (r, g, b)


def color_distance(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def reduce_palette(img, n_colors):
    img_quantized = img.convert(
        "P", palette=Image.ADAPTIVE, colors=n_colors, dither=Image.FLOYDSTEINBERG
    )
    return img_quantized.convert("RGB")


def load_tiles(tile_dir):
    tile_files = sorted(
        [f for f in os.listdir(tile_dir) if f.endswith(".png")],
        key=lambda s: int(re.findall(r"\d+", s)[0]),
    )

    colors = []
    for f in tile_files:
        img = Image.open(os.path.join(tile_dir, f)).convert("RGB")
        colors.append(avg_rgb(img))

    print(Fore.GREEN + f"[!] Loaded {len(tile_files)} tiles!" + Style.RESET_ALL)
    return colors, tile_files


def pick_best_tile(rgb, tile_colors):
    best_idx = 0
    best_dist = float("inf")

    for idx, tile_color in enumerate(tile_colors):
        dist = color_distance(rgb, tile_color)
        if dist < best_dist:
            best_dist = dist
            best_idx = idx

    return best_idx


def convert_image(img_path, tile_colors):
    img = Image.open(img_path).convert("RGB")
    print(
        Fore.CYAN
        + f"[+] Reducing palette to {PALETTE_COLORS} colors..."
        + Style.RESET_ALL
    )
    img = reduce_palette(img, PALETTE_COLORS)

    w, h = img.size
    print(Fore.CYAN + f"[+] Converting {w}x{h} Image to Tiles..." + Style.RESET_ALL)

    ids = []
    unique_colors = {}

    for y in range(h):
        for x in range(w):
            rgb = img.getpixel((x, y))
            if rgb not in unique_colors:
                unique_colors[rgb] = pick_best_tile(rgb, tile_colors)

            ids.append(unique_colors[rgb])

    print(
        Fore.GREEN
        + f"[!] Mapped {len(unique_colors)} unique colors to tiles!"
        + Style.RESET_ALL
    )
    return ids, w, h


def build_preview(tile_ids, w, h, tile_files):
    tile_imgs = [
        Image.open(os.path.join(TILE_DIR, f)).convert("RGB") for f in tile_files
    ]
    MAX_PREVIEW_SIZE = 2000

    TILE_SIZE = min(50, MAX_PREVIEW_SIZE // max(w, h))
    TILE_SIZE = max(1, TILE_SIZE)

    print(
        Fore.YELLOW
        + f"[-] Using {TILE_SIZE}x{TILE_SIZE}px tiles for preview"
        + Style.RESET_ALL
    )
    preview = Image.new("RGB", (w * TILE_SIZE, h * TILE_SIZE))

    for y in range(h):
        for x in range(w):
            tile_index = tile_ids[y * w + x]
            tile_img = tile_imgs[tile_index]

            # because i suck, some of em are 49x50 instead of 50x50...oopsies!
            tile_img = tile_img.resize((TILE_SIZE, TILE_SIZE), Image.NEAREST)

            preview.paste(tile_img, (x * TILE_SIZE, y * TILE_SIZE))

    return preview


def write_mpx(path, tile_ids, w, h, name):
    header = bytearray()
    header.extend(b"MPX ")
    header.extend((1).to_bytes(2, "little"))
    header.extend((1).to_bytes(2, "little"))

    # dimensions
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

    # write file
    with open(path, "wb") as f:
        f.write(header)
        f.write(bytes(tile_ids))
        f.write(info)

    print(
        Fore.MAGENTA
        + f"[!] Wrote {path} ({len(header) + body_len} bytes)"
        + Style.RESET_ALL
    )


def start_conversion():
    global TILE_DIR, INPUT_IMAGE, LEVEL_NAME, OUTPUT_MPX, PALETTE_COLORS

    INPUT_IMAGE = selected_image_var.get()
    LEVEL_NAME = level_name_var.get() if level_name_var.get() else "Untitled Level"
    OUTPUT_MPX = f"{output_filename_var.get()}.mpx"
    PALETTE_COLORS = palette_count_var.get()

    if not INPUT_IMAGE or INPUT_IMAGE == "File Name:":
        messagebox.showerror("Error", "Please select an input image first!")
        return
    progress["value"] = 0
    progress["maximum"] = 100
    root.update_idletasks()
    tile_colors, tile_files = load_tiles(TILE_DIR)
    progress["value"] = 20
    root.update_idletasks()
    tile_ids, W, H = convert_image(INPUT_IMAGE, tile_colors)
    progress["value"] = 50
    root.update_idletasks()
    write_mpx(OUTPUT_MPX, tile_ids, W, H, LEVEL_NAME)
    progress["value"] = 70
    root.update_idletasks()
    print(Fore.GREEN + "[!] Conversion Complete!" + Style.RESET_ALL)
    preview_img = build_preview(tile_ids, W, H, tile_files)
    progress["value"] = 90
    root.update_idletasks()

    preview_img.save("preview.png")
    canvas_w = 490
    canvas_h = 300
    img_w, img_h = preview_img.size
    scale = min(canvas_w / img_w, canvas_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    preview_img = preview_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    tk_img = ImageTk.PhotoImage(preview_img)
    canvas.image = tk_img
    canvas.delete("all")
    canvas.create_image(canvas_w // 2, canvas_h // 2, image=tk_img, anchor=tk.CENTER)
    progress["value"] = 100
    root.update_idletasks()
    print(Fore.YELLOW + "[!] Preview image saved as preview.png" + Style.RESET_ALL)


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
ttk.Spinbox(left, from_=1, to=100, textvariable=palette_count_var).place(
    x=210, y=100, width=185, height=35
)

select_frame = ttk.Labelframe(left, text="Select Input Image")
select_frame.place(x=10, y=140, width=380, height=85)

ttk.Button(select_frame, text="Select Image", command=select_image).place(
    x=10, y=20, width=106, height=35
)

filename_label = ttk.Label(select_frame, text=selected_image_var.get(), anchor="w")
filename_label.place(x=120, y=20, width=246, height=35)

ttk.Separator(left).place(x=10, y=232, width=380)

progress = ttk.Progressbar(left, mode="determinate")
progress.place(x=10, y=240, width=240, height=35)

ttk.Button(left, text="Start Conversion", command=start_conversion).place(
    x=260, y=240, width=130, height=35
)

canvas = tk.Canvas(root, background="#18191b")
canvas.place(x=420, y=20, width=490, height=300)


def set_dpi_aware(root):
    try:
        if sys.platform == "win32":
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.user32.SetProcessDPIAware()
        monitor_dpi = root.winfo_fpixels("1i")
        scaling_factor = max(1.0, monitor_dpi / 96.0) * 1.7
        root.tk.call("tk", "scaling", scaling_factor)
    except Exception as e:
        print(f"Failed to set DPI awareness: {e}")


set_dpi_aware(root)
apply_theme_to_titlebar(root)
root.mainloop()
