// Links packaging/isoc23-shim.c into the binaries when the static ONNX
// Runtime is in use, so they stop importing GLIBC_2.38 (issue #32). See the
// C file for the full story.
fn main() {
    println!("cargo:rerun-if-changed=packaging/isoc23-shim.c");
    println!("cargo:rerun-if-changed=build.rs");

    // `ort-defaults` = static libonnxruntime.a from ort-sys. The CUDA
    // packages use `load-dynamic` instead and never reference the symbols.
    if std::env::var_os("CARGO_FEATURE_ORT_DEFAULTS").is_none() {
        return;
    }

    let out_dir = std::env::var("OUT_DIR").unwrap();
    cc::Build::new()
        .file("packaging/isoc23-shim.c")
        // Pin the C dialect: GCC 15 (Arch, Fedora 43+) defaults to gnu23,
        // where glibc redirects strtol() to __isoc23_strtol() and each
        // wrapper in the shim would call itself. The #error in the C file
        // catches the same mistake if this flag ever gets dropped.
        .flag("-std=gnu17")
        .cargo_metadata(false)
        .compile("isoc23_shim");

    // The static ONNX Runtime archive comes later on the link line than a
    // plain `-l static=isoc23_shim` would, so the linker would skip our
    // archive (nothing references it yet) and leave the symbols to libc.
    // Forcing the whole archive in at the end resolves them regardless of
    // order. `rustc-link-arg` (not `-bins`) so `cargo test` links too: the
    // lib test binary pulls in the same static ONNX Runtime.
    println!("cargo:rustc-link-search=native={out_dir}");
    println!("cargo:rustc-link-arg=-Wl,--whole-archive");
    println!("cargo:rustc-link-arg=-l:libisoc23_shim.a");
    println!("cargo:rustc-link-arg=-Wl,--no-whole-archive");
}
