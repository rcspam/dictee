//! Mid-run GPU resilience state for the diarization ONNX sessions.
//!
//! VRAM on consumer GPUs is first-come-first-served with no OS arbitration:
//! an external GPU consumer (e.g. an LLM runtime like Ollama) can exhaust it
//! while a long diarization is running, and the in-flight inference then
//! fails hard. The binaries' init-time CPU retry does not cover that window.
//!
//! Both diarization models process audio in independent 10 s windows, which
//! makes per-window recovery natural:
//!   1. a GPU inference failure rebuilds the session on CPU and retries the
//!      failed window — the run degrades instead of dying;
//!   2. while degraded, the model periodically (with exponential backoff)
//!      tries to rebuild on the preferred provider and moves back to the GPU
//!      once VRAM is available again (e.g. after the LLM idle-unloads).

use std::path::PathBuf;

use crate::execution::{ExecutionProvider, ModelConfig as ExecutionConfig};

/// Windows to wait before the first GPU re-probe (~1 min of audio in live
/// mode; a few seconds of wall time in batch mode).
const PROBE_INITIAL: u64 = 60;
/// Backoff cap so a busy GPU is still re-tried every ~30 min of audio.
const PROBE_MAX: u64 = 1920;

pub(crate) struct GpuResilience {
    pub(crate) model_path: PathBuf,
    /// Preferred (possibly GPU) session config, kept for re-probes.
    pub(crate) exec_config: ExecutionConfig,
    pub(crate) on_cpu: bool,
    windows_since_probe: u64,
    probe_after: u64,
    windows_run: u64,
    /// Test hook: DICTEE_DIAR_FAIL_WINDOW=<n> makes the n-th GPU window of
    /// each model fail artificially, to exercise the fallback/resume path.
    fail_at: Option<u64>,
    label: &'static str,
}

impl GpuResilience {
    pub(crate) fn new(
        label: &'static str,
        model_path: PathBuf,
        exec_config: ExecutionConfig,
    ) -> Self {
        let fail_at = std::env::var("DICTEE_DIAR_FAIL_WINDOW")
            .ok()
            .and_then(|v| v.parse().ok());
        Self {
            model_path,
            exec_config,
            on_cpu: false,
            windows_since_probe: 0,
            probe_after: PROBE_INITIAL,
            windows_run: 0,
            fail_at,
            label,
        }
    }

    pub(crate) fn label(&self) -> &'static str {
        self.label
    }

    pub(crate) fn gpu_preferred(&self) -> bool {
        self.exec_config.execution_provider != ExecutionProvider::Cpu
    }

    pub(crate) fn cpu_config(&self) -> ExecutionConfig {
        self.exec_config
            .clone()
            .with_execution_provider(ExecutionProvider::Cpu)
    }

    /// Counts a window run; true when the test hook wants this one to fail.
    pub(crate) fn inject_failure(&mut self) -> bool {
        self.windows_run += 1;
        !self.on_cpu && self.fail_at == Some(self.windows_run)
    }

    /// True when a degraded model should try to go back to the GPU now.
    pub(crate) fn should_probe_gpu(&mut self) -> bool {
        if !self.on_cpu || !self.gpu_preferred() {
            return false;
        }
        self.windows_since_probe += 1;
        self.windows_since_probe >= self.probe_after
    }

    pub(crate) fn mark_cpu(&mut self) {
        self.on_cpu = true;
        self.windows_since_probe = 0;
        self.probe_after = PROBE_INITIAL;
    }

    pub(crate) fn probe_failed(&mut self) {
        self.windows_since_probe = 0;
        self.probe_after = (self.probe_after * 2).min(PROBE_MAX);
    }

    pub(crate) fn mark_gpu(&mut self) {
        self.on_cpu = false;
        self.windows_since_probe = 0;
        self.probe_after = PROBE_INITIAL;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_probe_when_cpu_is_the_preferred_provider() {
        let mut c = GpuResilience::new("cpu", PathBuf::from("/x"), ExecutionConfig::new());
        c.mark_cpu();
        assert!(!c.should_probe_gpu()); // CPU-only config: nothing to resume
    }

    // GPU-preferred behavior needs a non-CPU provider variant, which is
    // feature-gated (cuda). CI runs the cpu feature set; the cuda dev builds
    // exercise these.
    #[cfg(feature = "cuda")]
    mod gpu {
        use super::super::*;

        fn res() -> GpuResilience {
            let cfg = ExecutionConfig::new()
                .with_execution_provider(ExecutionProvider::Cuda);
            GpuResilience::new("test", PathBuf::from("/nonexistent"), cfg)
        }

        #[test]
        fn probe_backoff_doubles_and_caps() {
            let mut r = res();
            r.mark_cpu();
            for _ in 0..PROBE_INITIAL - 1 {
                assert!(!r.should_probe_gpu());
            }
            assert!(r.should_probe_gpu());
            r.probe_failed();
            for _ in 0..2 * PROBE_INITIAL - 1 {
                assert!(!r.should_probe_gpu());
            }
            assert!(r.should_probe_gpu());
            for _ in 0..20 {
                r.probe_failed();
            }
            assert_eq!(r.probe_after, PROBE_MAX);
        }

        #[test]
        fn no_probe_while_healthy_on_gpu() {
            let mut r = res();
            assert!(!r.should_probe_gpu());
        }

        #[test]
        fn resume_resets_backoff() {
            let mut r = res();
            r.mark_cpu();
            r.probe_failed();
            r.probe_failed();
            r.mark_gpu();
            r.mark_cpu();
            assert_eq!(r.probe_after, PROBE_INITIAL);
        }
    }
}
