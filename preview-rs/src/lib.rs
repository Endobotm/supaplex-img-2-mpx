use pyo3::prelude::*;
#[pymodule]
mod preview_rs {
    use anyhow::Result;
    use image::{ImageBuffer, RgbImage, imageops};
    use natord;
    use num::integer::div_floor;
    use pyo3::prelude::*;
    use std::cmp;
    use std::fs;
    fn load_tiles_from_dir(tile_dir: &str) -> Result<Vec<RgbImage>> {
        let mut tiles: Vec<ImageBuffer<image::Rgb<u8>, Vec<u8>>> = Vec::new();

        let paths: fs::ReadDir = fs::read_dir(tile_dir)?;

        let mut entries: Vec<_> = paths
            .filter_map(|e: Result<fs::DirEntry, std::io::Error>| e.ok())
            .filter(|e: &fs::DirEntry| {
                e.path()
                    .extension()
                    .and_then(|s: &std::ffi::OsStr| s.to_str())
                    .map(|s| s.eq_ignore_ascii_case("png"))
                    .unwrap_or(false)
            })
            .collect();

        entries.sort_by(|a, b| {
            natord::compare(a.path().to_str().unwrap(), b.path().to_str().unwrap())
        });

        for entry in entries {
            let img: ImageBuffer<image::Rgb<u8>, Vec<u8>> = image::open(entry.path())?.to_rgb8();
            tiles.push(img);
        }

        Ok(tiles)
    }
    #[pyfunction]
    fn generate_preview(
        tile_ids: Vec<u8>,
        w: usize,
        h: usize,
        tile_dir: String,
        default_tile_wh: Vec<i32>,
    ) -> PyResult<Vec<u8>> {
        let tile_imgs: Vec<ImageBuffer<image::Rgb<u8>, Vec<u8>>> =
            load_tiles_from_dir(&tile_dir)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;
        const MAX_PREVIEW: i32 = 4000;
        let tile_size: i32 = cmp::min(
            default_tile_wh[0],
            cmp::max(
                5,
                div_floor(
                    MAX_PREVIEW,
                    cmp::max(w.try_into().unwrap(), h.try_into().unwrap()),
                ),
            ),
        );
        let mut preview: RgbImage = ImageBuffer::new(
            (w * tile_size as usize) as u32,
            (h * tile_size as usize) as u32,
        );

        for y in 0..h {
            for x in 0..w {
                let idx = tile_ids[y * w + x] as usize;
                if idx >= tile_imgs.len() {
                    continue;
                }
                let tile_resized: ImageBuffer<image::Rgb<u8>, Vec<u8>> = imageops::resize(
                    &tile_imgs[idx],
                    tile_size as u32,
                    tile_size as u32,
                    imageops::FilterType::Nearest,
                );
                imageops::replace(
                    &mut preview,
                    &tile_resized,
                    (x * tile_size as usize) as i64,
                    (y * tile_size as usize) as i64,
                );
            }
        }
        Ok(preview.into_raw())
    }
}
