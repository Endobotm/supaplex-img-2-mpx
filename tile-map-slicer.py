from __future__ import print_function
from PIL import Image
import numpy as np
import os
from collections import Counter
import binascii
import struct
import scipy
import scipy.cluster

NUM_CLUSTERS = 5

INPUT = "tilemap.png"
OUTPUT_DIR = "tiles"

MAGENTA = (255, 71, 251)

os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_true_dominant_color(img):
    ar = np.asarray(img).astype(float)
    h, w, c = ar.shape
    ar = ar.reshape(h * w, c)
    print("finding clusters...")
    ar = ar.astype(np.float32)
    codes, dist = scipy.cluster.vq.kmeans(ar, NUM_CLUSTERS)
    vecs, dist = scipy.cluster.vq.vq(ar, codes)
    counts = np.bincount(vecs)
    index_max = np.argmax(counts)
    peak = codes[index_max]
    peak_int = tuple(int(p) for p in peak)
    colour_hex = binascii.hexlify(bytearray(peak_int)).decode("ascii")

    return peak_int, colour_hex


img = Image.open(INPUT).convert("RGB")
w, h = img.size
pixels = np.array(img)

is_magenta_col = [
    all(tuple(pixels[y, x]) == MAGENTA for y in range(h)) for x in range(w)
]

separators = []
in_sep = False
start = 0

for x, is_sep in enumerate(is_magenta_col):
    if is_sep and not in_sep:
        in_sep = True
        start = x
    elif not is_sep and in_sep:
        in_sep = False
        separators.append((start, x))

if in_sep:
    separators.append((start, w))

tiles = []
last_end = 0

for sep_start, sep_end in separators:
    if sep_start > last_end:
        tiles.append((last_end, sep_start))
    last_end = sep_end

if last_end < w:
    tiles.append((last_end, w))

for i, (x0, x1) in enumerate(tiles):
    tile = img.crop((x0, 0, x1, h))
    tile.save(f"{OUTPUT_DIR}/tile_{i}.png")

    dom = get_true_dominant_color(tile)
    print(f"Tile {i}: width={x1-x0}px, dominant_color={dom}")
