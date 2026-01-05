# Building Skia Graphite with WebGPU/Dawn for WebAssembly

This document captures the learnings from getting Skia's Graphite GPU backend working with WebGPU in a WASM environment.

## Overview

Skia has two GPU backends:
- **Ganesh** (legacy): Uses OpenGL/WebGL, Metal, Vulkan, Direct3D
- **Graphite** (new): Uses Dawn (which provides WebGPU, Metal, Vulkan, D3D12)

For WASM/WebGPU, Graphite + Dawn is the path forward, but there are significant compatibility challenges.

## Critical Findings

### 1. Skia Branch Compatibility

**Problem**: Skia's `main` branch has Dawn/Tint API mismatches that cause build failures:
```
error: no type named 'Bindings' in namespace 'tint'
error: no member named 'ExternalTexture' in namespace 'tint'
```

**Solution**: Use stable `chrome/*` branches (e.g., `chrome/m132`, `chrome/m144`) which have matching Dawn/Tint versions. The CI workflow uses `chrome/m144` by default.

```bash
# The CI default (check .github/workflows/build-skia.yml for SKIA_BRANCH)
python3 build-skia.py wasm -variant graphite -config Release

# Or specify a branch explicitly
python3 build-skia.py wasm -variant graphite -branch chrome/m144 -config Release
```

### 2. Emscripten Version Matters

Skia bundles its own Emscripten SDK at:
```
build/src/skia/third_party/externals/emsdk/
```

**Skia's Emscripten (3.1.44)** uses:
- `-sUSE_WEBGPU=1` flag
- `emscripten/html5_webgpu.h` header
- `emscripten_webgpu_get_device()` function
- SwapChain-based rendering

**Newer Emscripten (4.0+)** uses:
- `--use-port=emdawnwebgpu` flag
- `webgpu/webgpu.h` and `webgpu/webgpu_cpp.h` headers
- Async adapter/device request with callbacks
- Surface configuration (no SwapChain)

**Recommendation**: Use Skia's bundled Emscripten for building the example to ensure API compatibility with how Skia was built.

### 3. GN Args for Graphite/WebGPU WASM

The critical GN arguments for building Skia with Graphite/WebGPU:

```gn
# Graphite/WebGPU configuration (critical)
skia_enable_ganesh = false
skia_enable_graphite = true
skia_use_dawn = true
skia_use_webgpu = true
skia_use_webgl = false
skia_use_gl = false
skia_use_angle = false
skia_use_vulkan = false
```

When `skia_use_dawn = true`, Skia's build system will:
1. Build Dawn via CMake (in `third_party/dawn/BUILD.gn`)
2. Build Tint shader compiler as part of Dawn
3. Link the Dawn WebGPU implementation

### 4. Required Headers

For chrome/m132 with Skia's Emscripten:

```cpp
// Emscripten WebGPU bindings
#include <emscripten/html5_webgpu.h>
#include <webgpu/webgpu_cpp.h>

// Skia Graphite Dawn headers
#include "include/gpu/graphite/Context.h"
#include "include/gpu/graphite/ContextOptions.h"
#include "include/gpu/graphite/Recorder.h"
#include "include/gpu/graphite/Recording.h"
#include "include/gpu/graphite/Surface.h"
#include "include/gpu/graphite/BackendTexture.h"
#include "include/gpu/graphite/dawn/DawnBackendContext.h"
#include "include/gpu/graphite/dawn/DawnTypes.h"
#include "include/gpu/graphite/dawn/DawnUtils.h"
```

### 5. API Usage (chrome/m132 + Emscripten 3.1.44)

**Initialization pattern:**
```cpp
// Get device from JavaScript (set up via Module.preinitializedWebGPUDevice)
WGPUDevice device = emscripten_webgpu_get_device();
wgpu::Device g_device = wgpu::Device::Acquire(device);

// Create instance and surface
wgpu::Instance instance = wgpu::CreateInstance();
wgpu::SurfaceDescriptorFromCanvasHTMLSelector canvasDesc;
canvasDesc.selector = "#canvas";
wgpu::SurfaceDescriptor surfaceDesc;
surfaceDesc.nextInChain = &canvasDesc;
wgpu::Surface surface = instance.CreateSurface(&surfaceDesc);

// Create SwapChain (old API)
wgpu::SwapChainDescriptor swapChainDesc;
swapChainDesc.usage = wgpu::TextureUsage::RenderAttachment;
swapChainDesc.format = wgpu::TextureFormat::BGRA8Unorm;
swapChainDesc.width = width;
swapChainDesc.height = height;
swapChainDesc.presentMode = wgpu::PresentMode::Fifo;
wgpu::SwapChain swapChain = device.CreateSwapChain(surface, &swapChainDesc);

// Create Graphite context
skgpu::graphite::DawnBackendContext backendContext;
backendContext.fInstance = instance;
backendContext.fDevice = g_device;
backendContext.fQueue = g_device.GetQueue();
backendContext.fTick = webgpuTick;  // For ASYNCIFY

skgpu::graphite::ContextOptions options;
auto context = skgpu::graphite::ContextFactory::MakeDawn(backendContext, options);
auto recorder = context->makeRecorder();
```

**Rendering pattern:**
```cpp
// Get swapchain texture
wgpu::TextureView textureView = swapChain.GetCurrentTextureView();

// Create Skia texture info
skgpu::graphite::DawnTextureInfo textureInfo(
    /*sampleCount=*/1,
    skgpu::Mipmapped::kNo,
    wgpu::TextureFormat::BGRA8Unorm,
    wgpu::TextureUsage::RenderAttachment,
    wgpu::TextureAspect::All
);

// Wrap in BackendTexture
auto backendTexture = skgpu::graphite::BackendTextures::MakeDawn(
    SkISize::Make(width, height),
    textureInfo,
    textureView.Get()
);

// Create SkSurface
auto surface = SkSurfaces::WrapBackendTexture(
    recorder.get(),
    backendTexture,
    kBGRA_8888_SkColorType,
    SkColorSpace::MakeSRGB(),
    nullptr
);

// Draw to canvas
SkCanvas* canvas = surface->getCanvas();
// ... draw operations ...

// Submit
auto recording = recorder->snap();
skgpu::graphite::InsertRecordingInfo info;
info.fRecording = recording.get();
context->insertRecording(info);
context->submit(skgpu::graphite::SyncToCpu::kNo);

swapChain.Present();
```

### 6. CMake/Emscripten Flags

```cmake
# Compile flags
target_compile_options(example PRIVATE "-sUSE_WEBGPU=1")

# Link flags
target_link_options(example PRIVATE
    "-sUSE_WEBGPU=1"
    "-sUSE_WEBGL2=0"
    "-sASYNCIFY"
    "-sASYNCIFY_STACK_SIZE=65536"
    "--closure=0"  # Incompatible with ASYNCIFY
    "-sALLOW_MEMORY_GROWTH=1"
    "-sINITIAL_MEMORY=128MB"
)
```

### 7. HTML Shell Requirements

The HTML shell must initialize WebGPU before WASM loads:

```javascript
async function initWebGPU() {
    if (!navigator.gpu) {
        throw new Error('WebGPU not supported');
    }
    const adapter = await navigator.gpu.requestAdapter();
    const device = await adapter.requestDevice();
    Module.preinitializedWebGPUDevice = device;
}

// Call before instantiating WASM
await initWebGPU();
```

### 8. ASYNCIFY for WebGPU

ASYNCIFY is required because WebGPU operations are async in JavaScript. The tick function allows yielding:

```cpp
EM_ASYNC_JS(void, asyncSleep, (), {
    await new Promise((resolve, _) => {
        setTimeout(resolve, 0);
    });
});

void webgpuTick(const wgpu::Instance& instance) {
    asyncSleep();
}
```

Set `backendContext.fTick = webgpuTick;` to enable yielding.

## Build Commands

```bash
# Build Skia with Graphite/WebGPU
python3 build-skia.py wasm -variant graphite -branch chrome/m132 -config Release

# Build example using Skia's Emscripten
SKIA_EMSDK="build/src/skia/third_party/externals/emsdk"
export EM_CONFIG="$SKIA_EMSDK/.emscripten"
export PATH="$SKIA_EMSDK/upstream/emscripten:$SKIA_EMSDK/upstream/bin:$SKIA_EMSDK/node/16.20.0_64bit/bin:$PATH"

cd example
mkdir -p build-wasm-graphite && cd build-wasm-graphite
emcmake cmake .. -DCMAKE_BUILD_TYPE=Release -DUSE_GRAPHITE=ON
cmake --build .

# Serve
python3 -m http.server 8080
# Open http://localhost:8080/example.html in Chrome/Edge
```

## Troubleshooting

### Dawn/Tint build errors
Use a stable `chrome/m*` branch instead of `main`.

### "USE_WEBGPU" not found error
Your Emscripten is too new (4.0+). Use Skia's bundled Emscripten 3.1.44.

### Undefined symbol: vtable for DawnTextureInfo
Ensure `skia_use_dawn = true` in GN args. The Dawn backend code must be compiled.

### WebGPU not available in browser
Use Chrome or Edge with WebGPU enabled. Firefox support is experimental.

## Output Sizes (Release build)

- `example.wasm`: ~4.7 MB
- `example.js`: ~97 KB
- `example.html`: ~3.3 KB

## Browser Requirements

- Chrome 113+ or Edge 113+ (WebGPU enabled by default)
- Firefox Nightly with `dom.webgpu.enabled` flag
- Safari 18+ (macOS Sequoia / iOS 18)
