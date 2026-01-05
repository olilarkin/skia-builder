#!/bin/bash
# Apply Skia Graphite/WebGPU WASM patches
# Run from the skia-builder root directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SKIA_DIR="$ROOT_DIR/build/src/skia"
EMSDK_DIR="$SKIA_DIR/third_party/externals/emsdk"
LIBRARY_WEBGPU="$EMSDK_DIR/upstream/emscripten/src/library_webgpu.js"
DAWN_CAPS="$SKIA_DIR/src/gpu/graphite/dawn/DawnCaps.cpp"

echo "Applying patches for Skia Graphite/WebGPU WASM..."
echo "Root directory: $ROOT_DIR"

# Check files exist
if [ ! -f "$LIBRARY_WEBGPU" ]; then
    echo "ERROR: library_webgpu.js not found at $LIBRARY_WEBGPU"
    echo "Make sure Skia has been built with the graphite variant first."
    exit 1
fi

if [ ! -f "$DAWN_CAPS" ]; then
    echo "ERROR: DawnCaps.cpp not found at $DAWN_CAPS"
    exit 1
fi

# Backup original files
echo "Creating backups..."
cp "$LIBRARY_WEBGPU" "$LIBRARY_WEBGPU.orig" 2>/dev/null || true
cp "$DAWN_CAPS" "$DAWN_CAPS.orig" 2>/dev/null || true

# Check if patches already applied
if grep -q "|| size === -1" "$LIBRARY_WEBGPU"; then
    echo "library_webgpu.js: Patches appear to already be applied (found -1 check)"
else
    echo "Patching library_webgpu.js..."

    # Patch 1: Fix WHOLE_MAP_SIZE checks (3 locations)
    # Using perl for reliable multi-line replacement
    perl -i -pe 's/if \(size === \{\{\{ gpu\.WHOLE_MAP_SIZE \}\}\}\) size = undefined;/\/\/ Fix: Also check for -1 because SIZE_MAX (0xFFFFFFFF) can be interpreted as signed -1\n    if (size === {{{ gpu.WHOLE_MAP_SIZE }}} || size === -1) size = undefined;/g' "$LIBRARY_WEBGPU"

    echo "  - Fixed WHOLE_MAP_SIZE sentinel checks"
fi

# Patch 2: Fix setIndexBuffer - check if already patched
if grep -q "0xffffffffffffffffn" "$LIBRARY_WEBGPU"; then
    echo "library_webgpu.js: setIndexBuffer/setVertexBuffer already patched"
else
    # Patch setIndexBuffer
    perl -i -0pe 's/(wgpuRenderPassEncoderSetIndexBuffer: function\(passId, bufferId, format, offset, size\) \{)\s*\n\s*(var pass = WebGPU\.mgrRenderPassEncoder\.get\(passId\);)\s*\n\s*pass\["setIndexBuffer"\]\(WebGPU\.mgrBuffer\.get\(bufferId\), WebGPU\.IndexFormat\[format\], offset, size\);/$1\n    $2\n    var buffer = WebGPU.mgrBuffer.get(bufferId);\n    \/\/ Fix: Handle WGPU_WHOLE_SIZE sentinel value (-1 when sign-extended from 64-bit)\n    if (size === -1 || size === 0xffffffff || size === 0xffffffffffffffffn) size = undefined;\n    pass["setIndexBuffer"](buffer, WebGPU.IndexFormat[format], offset, size);/g' "$LIBRARY_WEBGPU"

    # Patch setVertexBuffer
    perl -i -0pe 's/(wgpuRenderPassEncoderSetVertexBuffer: function\(passId, slot, bufferId, offset, size\) \{)\s*\n\s*(var pass = WebGPU\.mgrRenderPassEncoder\.get\(passId\);)\s*\n\s*pass\["setVertexBuffer"\]\(slot, WebGPU\.mgrBuffer\.get\(bufferId\), offset, size\);/$1\n    $2\n    var buffer = WebGPU.mgrBuffer.get(bufferId);\n    \/\/ Fix: Handle WGPU_WHOLE_SIZE sentinel value (-1 when sign-extended from 64-bit)\n    if (size === -1 || size === 0xffffffff || size === 0xffffffffffffffffn) size = undefined;\n    pass["setVertexBuffer"](slot, buffer, offset, size);/g' "$LIBRARY_WEBGPU"

    echo "  - Fixed setIndexBuffer/setVertexBuffer sentinel checks"
fi

# Patch 3: Fix wgpuSwapChainPresent - check if already patched
if grep -q "No-op: Browsers auto-present" "$LIBRARY_WEBGPU"; then
    echo "library_webgpu.js: wgpuSwapChainPresent already patched"
else
    # Replace the abort with no-op
    perl -i -0pe 's/wgpuSwapChainPresent: function\(\) \{\s*\n#if ASSERTIONS\s*\n\s*abort\("wgpuSwapChainPresent is unsupported \(use requestAnimationFrame via html5\.h instead\)"\);\s*\n#endif\s*\n\s*\},/wgpuSwapChainPresent: function() {\n    \/\/ No-op: Browsers auto-present at the end of each requestAnimationFrame.\n    \/\/ When using emscripten_set_main_loop, the browser handles presentation automatically.\n  },/g' "$LIBRARY_WEBGPU"

    echo "  - Fixed wgpuSwapChainPresent to be no-op"
fi

# Patch 4: DawnCaps.cpp - check if already patched
if grep -q "__EMSCRIPTEN__" "$DAWN_CAPS" && grep -q "fUseAsyncPipelineCreation = false" "$DAWN_CAPS"; then
    # Check if our specific EMSCRIPTEN block exists
    if grep -A2 "__EMSCRIPTEN__" "$DAWN_CAPS" | grep -q "fUseAsyncPipelineCreation"; then
        echo "DawnCaps.cpp: EMSCRIPTEN patch already applied"
    else
        echo "Patching DawnCaps.cpp..."
        # Insert EMSCRIPTEN block after the !fTick block
        perl -i -0pe 's/(fAllowScopedErrorChecks = false;\s*\n\s*\})\s*\n(\s*fFullCompressedUploadSizeMustAlignToBlockDims)/$1\n\n#if defined(__EMSCRIPTEN__)\n    \/\/ For WASM\/Emscripten, always disable async pipeline creation even if fTick is set.\n    \/\/ CreateRenderPipelineAsync is not properly supported in Emscripten'\''s WebGPU bindings.\n    \/\/ Using synchronous CreateRenderPipeline lets the browser handle async internally.\n    fUseAsyncPipelineCreation = false;\n    fAllowScopedErrorChecks = false;\n#endif\n\n    $2/g' "$DAWN_CAPS"
        echo "  - Added EMSCRIPTEN block to disable async pipeline creation"
    fi
else
    echo "Patching DawnCaps.cpp..."
    perl -i -0pe 's/(fAllowScopedErrorChecks = false;\s*\n\s*\})\s*\n(\s*fFullCompressedUploadSizeMustAlignToBlockDims)/$1\n\n#if defined(__EMSCRIPTEN__)\n    \/\/ For WASM\/Emscripten, always disable async pipeline creation even if fTick is set.\n    \/\/ CreateRenderPipelineAsync is not properly supported in Emscripten'\''s WebGPU bindings.\n    \/\/ Using synchronous CreateRenderPipeline lets the browser handle async internally.\n    fUseAsyncPipelineCreation = false;\n    fAllowScopedErrorChecks = false;\n#endif\n\n    $2/g' "$DAWN_CAPS"
    echo "  - Added EMSCRIPTEN block to disable async pipeline creation"
fi

echo ""
echo "Patches applied successfully!"
echo ""
echo "Next steps:"
echo "  1. Rebuild the Skia library: python3 build-skia.py wasm -variant graphite -config Release"
echo "  2. Rebuild the example: make example-wasm-graphite"
echo "  3. Serve: make serve-wasm-graphite"
