//! G2 (`--features graphite`, Apple silicon): a window Graphite draws stands where the
//! CPU draws it. The works are the display's compatibility pictures without noise
//! (feTurbulence draws its grain differently on the GPU, as the 2026-10-11 survey
//! found; `alpha-mask-gray` is outside the support table), each whole at 1x and as a
//! 4x window off the centre, compared with the CPU window by the author's yardstick.
#![cfg(all(feature = "graphite", target_os = "macos"))]

use inku_display::{RasterRegionOptions, prepare_scene};
use inku_display_gpu::GpuWindows;

#[path = "../../inku-display/tests/common/difference.rs"]
mod comparison;
use comparison::{difference, over_white};

const WORKS: [&str; 4] = [
    "ellipse-gradient",
    "use-href",
    "pattern-href",
    "alpha-mask-white",
];

#[test]
fn gpu_windows_stand_where_the_cpu_draws_them() {
    let mut gpu = GpuWindows::new().expect("Graphite on this Mac");
    let mut compared = 0;
    for work in WORKS {
        let path = format!(
            "{}/../inku-display/tests/data/compat/{work}.svg",
            env!("CARGO_MANIFEST_DIR")
        );
        let scene = prepare_scene(&std::fs::read_to_string(&path).expect(&path)).unwrap();
        let (width, height) = (
            scene.intrinsic_width() as u32,
            scene.intrinsic_height() as u32,
        );
        for region in [
            RasterRegionOptions {
                full_width: width,
                full_height: height,
                x: 0,
                y: 0,
                width,
                height,
            },
            RasterRegionOptions {
                full_width: width * 4,
                full_height: height * 4,
                x: width,
                y: height * 3 / 4,
                width: width * 3 / 2,
                height: height * 5 / 4,
            },
        ] {
            let cpu = scene.region(region).unwrap();
            let drawn = gpu.draw(&scene, region).unwrap();
            assert_eq!((drawn.width, drawn.height), (region.width, region.height));
            let difference = difference(
                region.width as usize,
                region.height as usize,
                &over_white(&drawn),
                &over_white(&cpu),
            );
            eprintln!("{work} {region:?}: {difference:?}");
            assert!(difference.passes(), "{work} {region:?}: {difference:?}");
            compared += 1;
        }
    }
    assert_eq!(compared, 8);
}
