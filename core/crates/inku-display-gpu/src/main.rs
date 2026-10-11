//! `inku-display-gpu`: started by the macOS app on Apple silicon. Requests arrive on
//! standard input and pixels leave on standard output (`protocol`); diagnostics go to
//! standard error, which the app keeps for its display failure log.

use std::process::ExitCode;

#[cfg(all(feature = "graphite", target_os = "macos"))]
fn main() -> ExitCode {
    match inku_display_gpu::serve(std::io::stdin().lock(), std::io::stdout().lock()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("inku-display-gpu: {error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(not(all(feature = "graphite", target_os = "macos")))]
fn main() -> ExitCode {
    eprintln!("inku-display-gpu: built without Graphite (feature `graphite`, macOS only)");
    ExitCode::from(2)
}
