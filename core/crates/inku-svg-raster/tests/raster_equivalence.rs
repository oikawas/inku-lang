//! Run on the Linux testbox: compare the vendored renderer with pinned upstream.

use std::time::Instant;

use inku_svg_raster::{RasterOptions, rasterize};
use resvg_upstream::{tiny_skia, usvg};
use sha2::{Digest, Sha256};

#[test]
fn optimized_turbulence_preserves_upstream_images() {
    let cases = [
        (
            "filtered-pencil",
            include_str!(
                "../../../../server/reference/render-engine-41/C-filter-display-pencil.svg"
            ),
            1080,
        ),
        (
            "silver-shoal",
            include_str!("../../../../docs/assets/gallery/armistice-morning-silver-shoal.svg"),
            1080,
        ),
        (
            "parallel-full-region",
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="320" height="256"><defs><filter id="n" x="0" y="0" width="320" height="256" filterUnits="userSpaceOnUse"><feTurbulence type="fractalNoise" baseFrequency="0.07 0.11" numOctaves="3" seed="11"/></filter></defs><rect width="320" height="256" filter="url(#n)"/></svg>"#,
            320,
        ),
        (
            "stitched-negative-seed",
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="37" height="29"><defs><filter id="n" x="-13.5" y="7.25" width="37" height="29" filterUnits="userSpaceOnUse"><feTurbulence type="turbulence" baseFrequency="0.13 0.09" numOctaves="3" seed="-17" stitchTiles="stitch"/></filter></defs><rect width="37" height="29" filter="url(#n)"/></svg>"#,
            43,
        ),
        (
            "zero-octaves",
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="7" height="5"><defs><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0" numOctaves="0" seed="0"/></filter></defs><rect width="7" height="5" filter="url(#n)"/></svg>"#,
            7,
        ),
    ];

    for (name, svg, side) in cases {
        let started = Instant::now();
        let tree = usvg::Tree::from_str(svg, &usvg::Options::default()).expect("upstream parse");
        let intrinsic = tree.size();
        let scale = (f64::from(side) / f64::from(intrinsic.width()))
            .min(f64::from(side) / f64::from(intrinsic.height()));
        let width = (f64::from(intrinsic.width()) * scale).round().max(1.0) as u32;
        let height = (f64::from(intrinsic.height()) * scale).round().max(1.0) as u32;
        let mut expected = tiny_skia::Pixmap::new(width, height).expect("upstream pixels");
        resvg_upstream::render(
            &tree,
            tiny_skia::Transform::from_scale(scale as f32, scale as f32),
            &mut expected.as_mut(),
        );
        let upstream_ms = started.elapsed().as_secs_f64() * 1000.0;

        let started = Instant::now();
        let actual = rasterize(
            svg,
            RasterOptions {
                target_width: Some(side),
                target_height: Some(side),
            },
        )
        .expect("optimized raster");
        let optimized_ms = started.elapsed().as_secs_f64() * 1000.0;
        assert_eq!((actual.width, actual.height), (width, height), "{name}");
        assert_eq!(actual.stride, width * 4, "{name}");
        assert_eq!(actual.pixels.len(), expected.data().len(), "{name}");
        let changed_pixels = actual
            .pixels
            .chunks_exact(4)
            .zip(expected.data().chunks_exact(4))
            .filter(|(a, b)| a != b)
            .count();
        let digest: String = Sha256::digest(&actual.pixels)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        println!(
            "{name}: {width}x{height} upstream_ms={upstream_ms:.3} optimized_ms={optimized_ms:.3} changed_pixels={changed_pixels} sha256={digest}"
        );
        assert_eq!(
            changed_pixels, 0,
            "{name}: output changed from resvg 0.48.1"
        );
    }
}
