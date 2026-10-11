//! The macOS app's zoomed windows, drawn with Skia Graphite on Metal in a process of
//! their own (author's decisions, 2026-10-11): on Apple silicon the app starts
//! `inku-display-gpu`, writes each window's request to its standard input and reads
//! the pixels back. A GPU driver that ends this process does not end the app, which
//! logs the cause and leaves the window undrawn. The 100% picture stays on the CPU.
//!
//! Without the `graphite` feature (and off macOS) only the pipe format is built, and
//! the program says it cannot draw.

pub mod protocol;

#[cfg(all(feature = "graphite", target_os = "macos"))]
mod gpu;
#[cfg(all(feature = "graphite", target_os = "macos"))]
mod serve;

#[cfg(all(feature = "graphite", target_os = "macos"))]
pub use gpu::{GpuError, GpuWindows};
#[cfg(all(feature = "graphite", target_os = "macos"))]
pub use serve::{CHECK_ABORT_VARIABLE, serve};
