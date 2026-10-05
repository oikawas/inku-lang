//! Failure: immutable scene reuse changes filtered/clip pixels or outlives its owners.
use inku_svg_raster::{
    RasterError, RasterOptions, RasterRegionOptions, prepare_scene, rasterize, rasterize_region,
};
use std::sync::Arc;

const FILTER_CLIP: &str = r##"<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64"><defs><filter id="ink" x="-30%" y="-30%" width="160%" height="160%"><feTurbulence baseFrequency="0.06" numOctaves="2" seed="9" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="3"/><feGaussianBlur stdDeviation="0.5"/></filter><clipPath id="page"><rect x="4" y="3" width="86" height="57"/></clipPath></defs><g clip-path="url(#page)"><path d="M3 5h90v50H3z" fill="#e65932" filter="url(#ink)"/></g></svg>"##;

#[test]
fn immutable_scene_preserves_pixels_bounds_and_reference_lifetime() {
    fn send_sync<T: Send + Sync>() {}
    send_sync::<inku_svg_raster::PreparedScene>();
    let scene = Arc::new(prepare_scene(FILTER_CLIP).expect("scene"));
    assert_eq!(scene.source_bytes(), FILTER_CLIP.len() as u64);
    assert!(scene.cache_cost_bytes() > scene.source_bytes());
    let weak = Arc::downgrade(&scene);
    let options = RasterOptions {
        target_width: Some(192),
        target_height: Some(128),
    };
    let expected = rasterize(FILTER_CLIP, options).expect("one-shot");
    let shared = Arc::clone(&scene);
    let other_thread =
        std::thread::spawn(move || shared.rasterize(options).expect("thread-owned frame"));
    assert_eq!(other_thread.join().expect("thread"), expected);
    let region = RasterRegionOptions {
        full_width: 192,
        full_height: 128,
        x: 64,
        y: 32,
        width: 64,
        height: 64,
    };
    assert_eq!(
        scene.region(region).expect("region"),
        rasterize_region(FILTER_CLIP, region).expect("one-shot region")
    );
    let invalid = RasterOptions {
        target_width: Some(0),
        target_height: None,
    };
    assert_eq!(scene.rasterize(invalid), rasterize(FILTER_CLIP, invalid));
    let oversized = RasterOptions {
        target_width: Some(8192),
        target_height: Some(8192),
    };
    assert_eq!(
        scene.rasterize(oversized),
        rasterize(FILTER_CLIP, oversized)
    );
    let invalid_region = RasterRegionOptions { x: 191, ..region };
    assert_eq!(
        scene.region(invalid_region),
        rasterize_region(FILTER_CLIP, invalid_region)
    );
    assert_eq!(
        scene.region(invalid_region),
        Err(RasterError::InvalidTargetDimension)
    );
    drop(expected);
    drop(scene);
    assert!(
        weak.upgrade().is_none(),
        "last owner must release its immutable tree"
    );
}
