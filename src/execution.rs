use std::{fmt, rc::Rc};

use crate::error::Result;
use ort::session::builder::SessionBuilder;

// Hardware acceleration options. CPU is default and most reliable.
// GPU providers (CUDA, TensorRT, MIGraphX) offer 5-10x speedup but require specific hardware.
// All GPU providers automatically fall back to CPU if they fail.
//
// Note: CoreML currently fails with this model due to unsupported operations.
// WebGPU is experimental and may produce incorrect results.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ExecutionProvider {
    #[default]
    Cpu,
    #[cfg(feature = "cuda")]
    Cuda,
    #[cfg(feature = "tensorrt")]
    TensorRT,
    #[cfg(feature = "coreml")]
    CoreML,
    #[cfg(feature = "directml")]
    DirectML,
    #[cfg(feature = "migraphx")]
    MIGraphX,
    #[cfg(feature = "openvino")]
    OpenVINO,
    #[cfg(feature = "webgpu")]
    WebGPU,
    #[cfg(feature = "nnapi")]
    NNAPI,
}

#[derive(Clone)]
pub struct ModelConfig {
    pub execution_provider: ExecutionProvider,
    pub intra_threads: usize,
    pub inter_threads: usize,
    pub configure: Option<Rc<dyn Fn(SessionBuilder) -> ort::Result<SessionBuilder>>>,
}

impl fmt::Debug for ModelConfig {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ModelConfig")
            .field("execution_provider", &self.execution_provider)
            .field("intra_threads", &self.intra_threads)
            .field("inter_threads", &self.inter_threads)
            .field(
                "configure",
                &if self.configure.is_some() {
                    "<fn>"
                } else {
                    "None"
                },
            )
            .finish()
    }
}

impl Default for ModelConfig {
    fn default() -> Self {
        Self {
            execution_provider: ExecutionProvider::default(),
            intra_threads: 4,
            inter_threads: 1,
            configure: None,
        }
    }
}

impl ModelConfig {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_execution_provider(mut self, provider: ExecutionProvider) -> Self {
        self.execution_provider = provider;
        self
    }

    pub fn with_intra_threads(mut self, threads: usize) -> Self {
        self.intra_threads = threads;
        self
    }

    pub fn with_inter_threads(mut self, threads: usize) -> Self {
        self.inter_threads = threads;
        self
    }

    pub fn with_custom_configure(
        mut self,
        configure: impl Fn(SessionBuilder) -> ort::Result<SessionBuilder> + 'static,
    ) -> Self {
        self.configure = Some(Rc::new(configure));
        self
    }

    pub(crate) fn apply_to_session_builder(
        &self,
        builder: SessionBuilder,
    ) -> Result<SessionBuilder> {
        #[cfg(any(
            feature = "cuda",
            feature = "tensorrt",
            feature = "coreml",
            feature = "directml",
            feature = "migraphx",
            feature = "openvino",
            feature = "webgpu",
            feature = "nnapi"
        ))]
        use ort::ep::CPU as CPUExecutionProvider;
        use ort::session::builder::GraphOptimizationLevel;

        let mut builder = builder
            .with_optimization_level(GraphOptimizationLevel::Level3)?
            .with_intra_threads(self.intra_threads)?
            .with_inter_threads(self.inter_threads)?;

        builder = match self.execution_provider {
            ExecutionProvider::Cpu => builder,

            #[cfg(feature = "cuda")]
            ExecutionProvider::Cuda => builder.with_execution_providers([
                ort::ep::CUDA::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,

            #[cfg(feature = "tensorrt")]
            ExecutionProvider::TensorRT => builder.with_execution_providers([
                ort::ep::TensorRT::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,

            #[cfg(feature = "coreml")]
            ExecutionProvider::CoreML => {
                use ort::ep::coreml::{ComputeUnits, CoreML};
                builder.with_execution_providers([
                    CoreML::default()
                        .with_compute_units(ComputeUnits::CPUAndGPU)
                        .build(),
                    CPUExecutionProvider::default().build().error_on_failure(),
                ])?
            }

            #[cfg(feature = "directml")]
            ExecutionProvider::DirectML => builder.with_execution_providers([
                ort::ep::DirectML::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,

            #[cfg(feature = "migraphx")]
            ExecutionProvider::MIGraphX => builder.with_execution_providers([
                ort::ep::MIGraphX::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,

            #[cfg(feature = "openvino")]
            ExecutionProvider::OpenVINO => builder.with_execution_providers([
                ort::ep::OpenVINO::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,

            #[cfg(feature = "webgpu")]
            ExecutionProvider::WebGPU => builder.with_execution_providers([
                ort::ep::WebGPU::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,

            #[cfg(feature = "nnapi")]
            ExecutionProvider::NNAPI => builder.with_execution_providers([
                ort::ep::NNAPI::default().build(),
                CPUExecutionProvider::default().build().error_on_failure(),
            ])?,
        };

        if let Some(configure) = self.configure.as_ref() {
            builder = configure(builder)?;
        }

        Ok(builder)
    }
}

/// Probe whether a CUDA-capable GPU is actually usable on this host.
///
/// This is needed because the build-time `feature = "cuda"` flag only says
/// the binary *can* drive CUDA — it does not guarantee a working driver at
/// runtime. On a virtio VM, a headless container, or a host where the NVIDIA
/// kernel module is unloaded, asking ONNX Runtime for the CUDA provider
/// crashes deep inside `cudaSetDevice()` with code 35 ("driver insufficient")
/// and bypasses ort's own provider-list fallback.
///
/// Honors `DICTEE_FORCE_CPU` as a manual override.
#[cfg(feature = "cuda")]
pub fn cuda_runtime_available() -> bool {
    if std::env::var_os("DICTEE_FORCE_CPU").is_some() {
        return false;
    }
    // Primary probe: NVIDIA driver populates one dir per GPU under
    // /proc/driver/nvidia/gpus/<bus-id>/ when the kernel module is loaded.
    if let Ok(mut entries) = std::fs::read_dir("/proc/driver/nvidia/gpus") {
        if entries.next().is_some() {
            return true;
        }
    }
    // Secondary probe: /dev/nvidia0 character device, in case /proc is
    // restricted (sandboxes, certain container runtimes).
    std::path::Path::new("/dev/nvidia0").exists()
}

/// Pick the best execution provider available at runtime.
///
/// CUDA-enabled binaries call this instead of hard-wiring `Cuda`, so the
/// same artifact gracefully falls back to CPU on machines without a working
/// NVIDIA driver. Emits a one-line note on stderr when falling back.
pub fn best_provider() -> ExecutionProvider {
    #[cfg(feature = "cuda")]
    {
        if cuda_runtime_available() {
            return ExecutionProvider::Cuda;
        }
        eprintln!(
            "[dictee] No NVIDIA GPU detected (or DICTEE_FORCE_CPU set) — using CPU provider."
        );
    }
    ExecutionProvider::Cpu
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn best_provider_default_is_cpu_without_cuda_feature() {
        // When the cuda feature is off, best_provider() must always return Cpu.
        // When the cuda feature is on, the result depends on the host — we
        // only assert it returns *something* without panicking.
        let p = best_provider();
        #[cfg(not(feature = "cuda"))]
        assert_eq!(p, ExecutionProvider::Cpu);
        #[cfg(feature = "cuda")]
        let _ = p; // smoke test only
    }

    #[cfg(feature = "cuda")]
    #[test]
    fn force_cpu_env_var_disables_cuda() {
        // Save and restore env to be polite to other tests.
        let prev = std::env::var_os("DICTEE_FORCE_CPU");
        // SAFETY: tests run sequentially within this module by default; we
        // restore the variable below before returning.
        unsafe { std::env::set_var("DICTEE_FORCE_CPU", "1") };
        assert!(!cuda_runtime_available());
        match prev {
            Some(v) => unsafe { std::env::set_var("DICTEE_FORCE_CPU", v) },
            None => unsafe { std::env::remove_var("DICTEE_FORCE_CPU") },
        }
    }
}
