//! Whisper backend (whisper.cpp via whisper-rs, Vulkan GPU-only).
//! GPU-only by design: no CPU fallback (large-v3 on CPU is unusable; CPU is Parakeet's job).

/// Number of Vulkan devices ggml can see. Used at startup to decide whether
/// the Whisper backend is available at all (0 ⇒ unavailable, never CPU).
pub fn vulkan_device_count() -> i32 {
    whisper_rs::vulkan::list_devices().len() as i32
}
