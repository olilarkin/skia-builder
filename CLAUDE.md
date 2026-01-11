# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository provides a Python script and GitHub Actions workflow for building Skia static libraries for multiple platforms (macOS, iOS, visionOS, Windows, Linux, WASM). It automates build environment setup, Skia repository cloning, GN argument configuration, and compilation.

## Build Commands

Prerequisites: ninja, python3, cmake. On Windows, LLVM must be installed at `C:\Program Files\LLVM\`. On Linux, install build dependencies: `libfontconfig1-dev libgl1-mesa-dev libglu1-mesa-dev libx11-xcb-dev libwayland-dev`.

```bash
# May need to increase file limit on macOS first
ulimit -n 2048

# Build libraries directly
python3 build-skia.py mac                          # macOS universal (arm64 + x86_64)
python3 build-skia.py ios                          # iOS (arm64 + x86_64 simulator)
python3 build-skia.py visionos                     # visionOS (arm64)
python3 build-skia.py win                          # Windows x64
python3 build-skia.py linux                        # Linux x64
python3 build-skia.py wasm                         # WebAssembly
python3 build-skia.py xcframework                  # Apple XCFramework (macOS + iOS)

# Options
python3 build-skia.py <platform> -config Debug    # Debug build (default: Release)
python3 build-skia.py <platform> -branch chrome/m130  # Specific Skia branch
python3 build-skia.py <platform> --shallow        # Shallow clone
python3 build-skia.py <platform> -archs x86_64,arm64  # Specific architectures

# Windows (use py -3 or the build-win.sh helper)
py -3 build-skia.py win -config Release -branch chrome/m130
```

**Makefile shortcuts (from macOS):**
```bash
make skia-mac           # Build macOS libraries
make skia-ios           # Build iOS libraries
make skia-wasm          # Build WASM libraries
make skia-xcframework   # Build XCFramework
make example-mac        # Build and run example (./example/build-mac/example)
make example-wasm       # Build WASM example
make serve-wasm         # Serve WASM example on localhost:8080
make clean              # Remove build directory
```

## Architecture

**build-skia.py** - Main build script containing:
- `SkiaBuildScript` class orchestrating the entire build process
- GN argument constants (`RELEASE_GN_ARGS`, `PLATFORM_GN_ARGS`) defining Skia build configuration
- `LIBS` dict specifying which libraries to build per platform
- `PACKAGE_DIRS` defining which headers to copy to output

**Build output structure:**
```
build/
├── src/skia/          # Cloned Skia source
├── tmp/               # depot_tools, intermediate builds
├── include/           # Packaged headers
├── mac/lib/           # macOS libraries
├── ios/lib/           # iOS libraries (per-arch)
├── visionos/lib/      # visionOS libraries (arm64)
├── win/lib/           # Windows libraries
├── linux/lib/         # Linux libraries
├── wasm/lib/          # WASM libraries
└── xcframework/       # XCFramework output
```

**Key configuration:**
- `USE_LIBGRAPHEME` constant (line 81) toggles between libgrapheme and ICU for Unicode
- `MAC_MIN_VERSION` / `IOS_MIN_VERSION` set deployment targets
- `EXCLUDE_DEPS` lists Skia dependencies to skip during sync

## visionOS Support

visionOS builds use a workaround because **GN (Google's build tool) doesn't recognize visionOS/xros as a valid target OS**. This causes assertion failures in Skia's GN files (e.g., `third_party/zlib/BUILD.gn`).

**Our approach:** Use `target_os = "ios"` with explicit visionOS SDK and compiler flags:
- `-target arm64-apple-xros1.0` tells clang to use the visionOS target triple
- `-isysroot <path>` explicitly points to the visionOS SDK (obtained via `xcrun --sdk xros --show-sdk-path`)

The explicit sysroot is critical because `target_os = "ios"` causes GN to use the iOS SDK, but the iOS SDK's libc++ marks many functions as unavailable for visionOS (e.g., `__libcpp_verbose_abort`, `pthread_mutexattr_init`).

This approach was informed by research into:
- [react-native-skia #2280](https://github.com/Shopify/react-native-skia/issues/2280) - visionOS support blocked by GN limitations
- [react-native-webgpu #90](https://github.com/wcandillon/react-native-webgpu/pull/90) - successfully supports visionOS using CMake instead of GN

**Alternative approach (not used):** Build with CMake instead of GN, like react-native-webgpu does for Dawn. This would require significant changes to the build script.

## CI

The GitHub Actions workflow (`.github/workflows/build-skia.yml`) builds all platforms in parallel and creates releases tagged with the Skia branch name.

**Workflow inputs:**
- `skia_branch` - Skia branch to build (default: `chrome/m144`)
- `platforms` - Platforms to build, comma-separated or `all` (default: `all`)
- `skip_release` - Skip creating release, useful for testing (default: `false`)
- `test_mode` - Skip actual build, create dummy files (default: `false`)

```bash
# Build all platforms and create release
gh workflow run build-skia.yml

# Build specific platform(s) without release
gh workflow run build-skia.yml -f platforms=visionos -f skip_release=true
gh workflow run build-skia.yml -f platforms=mac,ios -f skip_release=true

# Build with different Skia branch
gh workflow run build-skia.yml -f skia_branch=chrome/m145

# Check CI status
gh run list
gh run view <run-id> --log-failed

# Create XCFramework from existing release (without rebuilding)
gh workflow run create-xcframework.yml -f release_tag=chrome/m144
```
