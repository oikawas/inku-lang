//! Regenerate `assets/work-plan-capabilities-v1.json` from the current compiler.
//!
//! ```sh
//! scripts/rust-toolchain.sh run -p inku-ddl --example work-plan-capabilities --locked --offline \
//!   > core/crates/inku-ddl/assets/work-plan-capabilities-v1.json
//! ```

fn main() {
    let capabilities = inku_ddl::work_plan::derive_work_plan_capabilities();
    println!(
        "{}",
        serde_json::to_string_pretty(&capabilities).expect("serialize capabilities")
    );
}
