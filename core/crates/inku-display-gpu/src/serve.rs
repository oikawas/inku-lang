//! Read requests, draw, answer, until the app closes the pipe.

use std::collections::HashMap;
use std::io::{self, BufReader, BufWriter, Read, Write};
use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_display::{DisplayScene, RasterRegionOptions, prepare_scene};

use crate::gpu::{GpuError, GpuWindows};
use crate::protocol::{self, Request, Response};

/// Summed weight of the kept scenes (Skia's picture estimate and the SVG), as the
/// app keeps its own (`DisplayRenderer`, 256 MiB). The newest scene is always kept.
const SCENE_COST_LIMIT: u64 = 256 * 1024 * 1024;

/// Set only by the app's checks to an SVG's SHA-256 (hex): a request for that SVG
/// stops the program, as a GPU driver that ends the process would.
pub const CHECK_ABORT_VARIABLE: &str = "INKU_DISPLAY_GPU_CHECK_ABORT";

pub fn serve(input: impl Read, output: impl Write) -> io::Result<()> {
    let mut input = BufReader::new(input);
    let mut output = BufWriter::with_capacity(1 << 20, output);
    let abort_for_check = std::env::var(CHECK_ABORT_VARIABLE).ok();
    let mut gpu: Option<Result<GpuWindows, GpuError>> = None;
    let mut scenes = Scenes::default();
    while let Some(request) = protocol::read_request(&mut input)? {
        if abort_for_check.as_deref() == Some(hex(&request.digest).as_str()) {
            eprintln!("inku-display-gpu: stopping for {CHECK_ABORT_VARIABLE}");
            std::process::abort();
        }
        let response = catch_unwind(AssertUnwindSafe(|| respond(&mut gpu, &mut scenes, request)))
            .unwrap_or_else(|_| {
                // Start the GPU objects afresh after a panic in the middle of a draw.
                gpu = None;
                Response::Failure {
                    code: "internal_invariant".to_owned(),
                    message: "inku-display-gpu panicked while drawing".to_owned(),
                }
            });
        protocol::write_response(&mut output, &response)?;
    }
    Ok(())
}

fn respond(
    gpu: &mut Option<Result<GpuWindows, GpuError>>,
    scenes: &mut Scenes,
    request: Request,
) -> Response {
    if let Some(svg) = request.svg {
        match prepare_scene(&svg) {
            Ok(scene) => scenes.keep(request.digest, scene, svg.len() as u64),
            Err(error) => return failure(error.into()),
        }
    }
    let Some(scene) = scenes.take(&request.digest) else {
        return Response::SceneMissing;
    };
    let windows = match gpu.get_or_insert_with(GpuWindows::new) {
        Ok(windows) => windows,
        Err(error) => {
            return Response::Failure {
                code: error.code.to_owned(),
                message: error.message.clone(),
            };
        }
    };
    let region = request.region;
    match windows.draw(
        scene,
        RasterRegionOptions {
            full_width: region.full_width,
            full_height: region.full_height,
            x: region.x,
            y: region.y,
            width: region.width,
            height: region.height,
        },
    ) {
        Ok(drawn) => Response::Image {
            width: drawn.width,
            height: drawn.height,
            stride: drawn.stride,
            pixels: drawn.pixels,
        },
        Err(error) => failure(error),
    }
}

fn hex(digest: &[u8; 32]) -> String {
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn failure(error: GpuError) -> Response {
    Response::Failure {
        code: error.code.to_owned(),
        message: error.message,
    }
}

#[derive(Default)]
struct Scenes {
    entries: HashMap<[u8; 32], Entry>,
    clock: u64,
}

struct Entry {
    scene: DisplayScene,
    cost: u64,
    used: u64,
}

impl Scenes {
    fn keep(&mut self, digest: [u8; 32], scene: DisplayScene, source_bytes: u64) {
        self.clock += 1;
        let cost = scene.picture_bytes() + source_bytes;
        self.entries.insert(
            digest,
            Entry {
                scene,
                cost,
                used: self.clock,
            },
        );
        let mut total: u64 = self.entries.values().map(|entry| entry.cost).sum();
        while total > SCENE_COST_LIMIT {
            let Some(oldest) = self
                .entries
                .iter()
                .filter(|(key, _)| **key != digest)
                .min_by_key(|(_, entry)| entry.used)
                .map(|(key, _)| *key)
            else {
                break;
            };
            total -= self.entries.remove(&oldest).map_or(0, |entry| entry.cost);
        }
    }

    fn take(&mut self, digest: &[u8; 32]) -> Option<&DisplayScene> {
        self.clock += 1;
        let entry = self.entries.get_mut(digest)?;
        entry.used = self.clock;
        Some(&entry.scene)
    }
}
