# SKIA BUILDER

This is a python script and github actions workflow to manage building static libraries for [SKIA](https://skia.org/).

![output](https://github.com/user-attachments/assets/b40cc273-272c-4f38-a64f-968327408fa5)

The script automates the process of building the libraries for various platforms (macOS, iOS, Windows, WASM). It handles the setup of the build environment, cloning of the Skia repository, configuration of build parameters, and compilation. The script also includes functionality for creating universal binaries for macOS and an XCFramework for apple platforms.

The GN Args are supplied in constants which you will need to tweak if you want to modify the build.

## Building

Skia's build scripts requires ninja and python3 to be installed on all platforms. Emscripten is installed via skia.

## Helper commands

There is a Makefile with helper commands to build the libraries for each platform (from macOS). On windows you can use the `build-win.sh` script.

```bash
make example-mac # Build example for macOS (will also build libSkia etc)
./example/build-mac/example
Image saved as output.png
```

Other options:
```bash
make skia-mac # Build libraries for macOS
make skia-ios # Build libraries for iOS
make skia-wasm # Build libraries for WASM
make skia-xcframework # Build XCFramework
make example-mac # Build example for macOS
make example-wasm # Build example for WASM
make serve-wasm # Serve the WASM example
```

## Build script

The script is called as follows

```
build-skia.py [-h] [-config {Debug,Release}] [-archs ARCHS] [-branch BRANCH] [--shallow] {mac,ios,win,spm,wasm}
```

## Building on macOS

Note: you may need to call 

```bash
ulimit -n 2048
```

in order to increase the number of files that can be opened at once.

Note: macOS builds target macOS 11+ (Big Sur). This is hardcoded in Skia's `gn/skia/BUILD.gn` via the `-target` compiler flag.

### Build for macOS universal (arm64 & x86_64 intel)

```bash
python3 build-skia.py -config Release -branch chrome/m129 mac
```

### Build for iOS (including x86_64 simulator)

```bash
python3 build-skia.py -config Release -branch chrome/m129 ios
```

### Build an XCFramework

```bash
python3 build-skia.py -config Release -branch chrome/m129 xcframework
```

## Building on Windows 

On Windows, you need to install LLVM in order to compile Skia with clang, as recommened by the authors.

LLVM should be installed in `C:\Program Files\LLVM\`

```bash
py -3 build-skia.py -config Release -branch chrome/m129 win
```

## CI / GitHub Actions

The repository includes a GitHub Actions workflow (`.github/workflows/build-skia.yml`) that builds all platforms in parallel and creates releases tagged with the Skia branch name.

### Workflow Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `skia_branch` | Skia branch to build | `chrome/m144` |
| `platforms` | Platforms to build (comma-separated or `all`) | `all` |
| `skip_release` | Skip creating release | `false` |
| `test_mode` | Skip build, create dummy files | `false` |

### Trigger Builds

```bash
# Build all platforms and create release
gh workflow run build-skia.yml

# Build specific platform(s) without creating a release
gh workflow run build-skia.yml -f platforms=visionos -f skip_release=true
gh workflow run build-skia.yml -f platforms=mac,ios -f skip_release=true
gh workflow run build-skia.yml -f platforms=win -f skip_release=true

# Build with a different Skia branch
gh workflow run build-skia.yml -f skia_branch=chrome/m145
```

### Check CI Status

```bash
gh run list
gh run view <run-id> --log-failed
```

### Create XCFramework from Existing Release

If you've already built all platforms, you can create an XCFramework without rebuilding:

```bash
gh workflow run create-xcframework.yml -f release_tag=chrome/m144
```

This downloads mac, ios, and visionos artifacts from the specified release and creates a combined XCFramework.
