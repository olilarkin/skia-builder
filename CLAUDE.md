# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository provides a Python script and GitHub Actions workflow for building Skia static libraries for multiple platforms (macOS, iOS, Windows, Linux, WASM). It automates build environment setup, Skia repository cloning, GN argument configuration, and compilation.

## Build Commands

Prerequisites: ninja, python3, cmake. On Windows, LLVM must be installed at `C:\Program Files\LLVM\`. On Linux, install build dependencies: `libfontconfig1-dev libgl1-mesa-dev libglu1-mesa-dev libx11-xcb-dev`.

```bash
# May need to increase file limit on macOS first
ulimit -n 2048

# Build libraries directly
python3 build-skia.py mac                          # macOS universal (arm64 + x86_64)
python3 build-skia.py ios                          # iOS (arm64 + x86_64 simulator)
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
├── win/lib/           # Windows libraries
├── linux/lib/         # Linux libraries
├── wasm/lib/          # WASM libraries
└── xcframework/       # XCFramework output
```

**Key configuration:**
- `USE_LIBGRAPHEME` constant (line 81) toggles between libgrapheme and ICU for Unicode
- `MAC_MIN_VERSION` / `IOS_MIN_VERSION` set deployment targets
- `EXCLUDE_DEPS` lists Skia dependencies to skip during sync

## CI

The GitHub Actions workflow (`.github/workflows/build-skia.yml`) builds all platforms in parallel and creates releases tagged with the Skia branch name. Change `SKIA_BRANCH` env var to target different Skia versions.
