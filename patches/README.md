# Skia Graphite/WebGPU WASM Patches

These patches are required to run Skia's Graphite GPU backend with WebGPU on WebAssembly.

## Tested Configuration

- **Skia branch**: `chrome/m132` through `chrome/m144` (stable chrome/* branches)
- **Emscripten**: 3.1.44 (bundled with Skia)
- **Browser**: Chrome/Edge with WebGPU enabled

> **Note**: These patches target the Emscripten version bundled with Skia. The CI workflow uses `chrome/m144` by default. Use stable `chrome/*` branches rather than `main` to avoid Dawn/Tint API mismatches.

## Patches

### 1. library_webgpu.js.patch

**Target**: `build/src/skia/third_party/externals/emsdk/upstream/emscripten/src/library_webgpu.js`

Fixes several issues in Emscripten's WebGPU JavaScript bindings:

1. **WGPU_WHOLE_MAP_SIZE handling**: The sentinel value `SIZE_MAX` (0xFFFFFFFF on 32-bit) gets sign-extended to `-1` when passed through JavaScript. The original code only checked for `0xFFFFFFFF`, causing `getMappedRange(-1)` errors.

2. **WGPU_WHOLE_SIZE handling**: Same issue for 64-bit size parameters in `setVertexBuffer` and `setIndexBuffer`.

3. **wgpuSwapChainPresent**: The original code had `abort()` in ASSERTIONS mode, but browsers auto-present at the end of each requestAnimationFrame. Changed to no-op.

### 2. DawnCaps.cpp.patch

**Target**: `build/src/skia/src/gpu/graphite/dawn/DawnCaps.cpp`

Disables async pipeline creation on Emscripten/WASM. Emscripten's WebGPU bindings don't properly support `CreateRenderPipelineAsync`, which causes fatal errors. Using synchronous `CreateRenderPipeline` works because the browser handles async internally.

## How to Apply

### Option A: Manual application

After building Skia with the graphite variant, apply the patches manually:

```bash
cd /path/to/skia-builder

# Apply library_webgpu.js patch
# (Lines numbers may vary - use search/replace based on context)
# Search for: if (size === {{{ gpu.WHOLE_MAP_SIZE }}}) size = undefined;
# Replace with: if (size === {{{ gpu.WHOLE_MAP_SIZE }}} || size === -1) size = undefined;
# (Apply to all 3 occurrences in wgpuBufferGetConstMappedRange, wgpuBufferGetMappedRange, wgpuBufferMapAsync)

# Search for the setVertexBuffer and setIndexBuffer functions and add sentinel checks

# Search for wgpuSwapChainPresent and replace the abort() with empty function body

# Apply DawnCaps.cpp patch - add EMSCRIPTEN block after the !fTick block
```

### Option B: Script-based application

Create an `apply-patches.sh` script:

```bash
#!/bin/bash
set -e

SKIA_DIR="build/src/skia"
EMSDK_DIR="$SKIA_DIR/third_party/externals/emsdk"
LIBRARY_WEBGPU="$EMSDK_DIR/upstream/emscripten/src/library_webgpu.js"
DAWN_CAPS="$SKIA_DIR/src/gpu/graphite/dawn/DawnCaps.cpp"

echo "Applying patches for Skia Graphite/WebGPU WASM..."

# Patch 1: Fix WHOLE_MAP_SIZE in wgpuBufferGetConstMappedRange
sed -i.bak 's/if (size === {{{ gpu.WHOLE_MAP_SIZE }}}) size = undefined;/\/\/ Fix: Also check for -1 because SIZE_MAX can be interpreted as signed -1\n    if (size === {{{ gpu.WHOLE_MAP_SIZE }}} || size === -1) size = undefined;/g' "$LIBRARY_WEBGPU"

# Patch 2: Fix setIndexBuffer
sed -i.bak '/wgpuRenderPassEncoderSetIndexBuffer/,/setIndexBuffer.*format.*offset.*size/c\
  wgpuRenderPassEncoderSetIndexBuffer: function(passId, bufferId, format, offset, size) {\
    var pass = WebGPU.mgrRenderPassEncoder.get(passId);\
    var buffer = WebGPU.mgrBuffer.get(bufferId);\
    // Fix: Handle WGPU_WHOLE_SIZE sentinel value (-1 when sign-extended from 64-bit)\
    if (size === -1 || size === 0xffffffff || size === 0xffffffffffffffffn) size = undefined;\
    pass["setIndexBuffer"](buffer, WebGPU.IndexFormat[format], offset, size);\
  },' "$LIBRARY_WEBGPU"

# Patch 3: Fix setVertexBuffer
sed -i.bak '/wgpuRenderPassEncoderSetVertexBuffer/,/setVertexBuffer.*slot.*buffer.*offset.*size/c\
  wgpuRenderPassEncoderSetVertexBuffer: function(passId, slot, bufferId, offset, size) {\
    var pass = WebGPU.mgrRenderPassEncoder.get(passId);\
    var buffer = WebGPU.mgrBuffer.get(bufferId);\
    // Fix: Handle WGPU_WHOLE_SIZE sentinel value (-1 when sign-extended from 64-bit)\
    if (size === -1 || size === 0xffffffff || size === 0xffffffffffffffffn) size = undefined;\
    pass["setVertexBuffer"](slot, buffer, offset, size);\
  },' "$LIBRARY_WEBGPU"

# Patch 4: Fix wgpuSwapChainPresent
sed -i.bak '/wgpuSwapChainPresent:/,/^  },/c\
  wgpuSwapChainPresent: function() {\
    // No-op: Browsers auto-present at the end of each requestAnimationFrame.\
  },' "$LIBRARY_WEBGPU"

# Patch 5: Add EMSCRIPTEN block in DawnCaps.cpp
sed -i.bak '/fAllowScopedErrorChecks = false;/,/fFullCompressedUploadSizeMustAlignToBlockDims/{
    /fFullCompressedUploadSizeMustAlignToBlockDims/i\
\
#if defined(__EMSCRIPTEN__)\
    // For WASM/Emscripten, always disable async pipeline creation even if fTick is set.\
    // CreateRenderPipelineAsync is not properly supported in Emscripten'\''s WebGPU bindings.\
    // Using synchronous CreateRenderPipeline lets the browser handle async internally.\
    fUseAsyncPipelineCreation = false;\
    fAllowScopedErrorChecks = false;\
#endif\

}' "$DAWN_CAPS"

echo "Patches applied successfully!"
echo "Now rebuild the example with: make example-wasm-graphite"
```

## Error Symptoms (Before Patches)

Without these patches, you'll see errors like:

1. `wgpuBufferGetMappedRange(0, -1) failed: Value is outside the 'unsigned long long' value range`
2. `CreateRenderPipelineAsync shouldn't be used in WASM` followed by fatal error
3. `Failed to execute 'setVertexBuffer' on 'GPURenderPassEncoder': Value is outside the 'unsigned long long' value range`
4. `wgpuSwapChainPresent is unsupported (use requestAnimationFrame via html5.h instead)`

## Notes

- These patches are specific to Emscripten 3.1.44 and Skia m132. Future versions may have different line numbers or may have fixed these issues upstream.
- The `library_webgpu.js` file is part of Emscripten, not Skia, so updates to Emscripten may require re-applying/adjusting patches.
- Consider contributing these fixes upstream to Emscripten and Skia.
