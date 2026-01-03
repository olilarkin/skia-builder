#!/usr/bin/env python3

"""
build-skia.py

This script automates the process of building Skia libraries for various platforms
(macOS, iOS, Windows, and Linux). It handles the setup of the build environment, cloning
of the Skia repository, configuration of build parameters, and compilation of the
libraries. The script also includes functionality for creating universal binaries
for macOS and a Swift Package and XCFramework for iOS.

Usage:
    python3 build-skia.py <platform> [options]

For detailed usage instructions, run:
    python3 build-skia.py --help

Copyright (c) 2024 Oli Larkin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Define ANSI color codes
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def colored_print(message, color):
    print(f"{color}{message}{Colors.ENDC}")

# Shared constants
BASE_DIR = Path(__file__).resolve().parent / "build"
DEPOT_TOOLS_PATH = BASE_DIR / "tmp" / "depot_tools"
DEPOT_TOOLS_URL = "https://chromium.googlesource.com/chromium/tools/depot_tools.git"
SKIA_GIT_URL = "https://github.com/google/skia.git"
SKIA_SRC_DIR = BASE_DIR / "src" / "skia"
TMP_DIR = BASE_DIR / "tmp" / "skia"
ACTIVATE_EMSDK_PATH = SKIA_SRC_DIR / "bin" / "activate-emsdk"

# Platform-specific library directories
MAC_LIB_DIR = BASE_DIR / "mac" / "lib"
IOS_LIB_DIR = BASE_DIR / "ios" / "lib"
WASM_LIB_DIR = BASE_DIR / "wasm" / "lib"
WIN_LIB_DIR = BASE_DIR / "win" / "lib"
LINUX_LIB_DIR = BASE_DIR / "linux" / "lib"

# Platform-specific constants
MAC_MIN_VERSION = "10.15"
IOS_MIN_VERSION = "13.0"

# Unicode backend configuration
USE_LIBGRAPHEME = False  # Set to True to use libgrapheme instead of ICU

# Shared libraries
LIBS = {
    "mac": [
        "libskia.a", "libskottie.a", "libskshaper.a", "libsksg.a",
        "libskparagraph.a", "libsvg.a", "libskunicode_core.a",
        "libskunicode_libgrapheme.a" if USE_LIBGRAPHEME else "libskunicode_icu.a"
    ],
    "ios": [
        "libskia.a", "libskottie.a", "libsksg.a", "libskshaper.a",
        "libskparagraph.a", "libsvg.a", "libskunicode_core.a",
        "libskunicode_libgrapheme.a" if USE_LIBGRAPHEME else "libskunicode_icu.a"
    ],
    "win": [
        "skia.lib", "skottie.lib", "sksg.lib", "skshaper.lib",
        "skparagraph.lib", "svg.lib", "skunicode_core.lib",
        "skunicode_libgrapheme.lib" if USE_LIBGRAPHEME else "skunicode_icu.lib"
    ],
    "wasm": [
        "libskia.a", "libskottie.a", "libskshaper.a", "libsksg.a",
        "libskparagraph.a", "libsvg.a", "libskunicode_core.a",
        "libskunicode_libgrapheme.a" if USE_LIBGRAPHEME else "libskunicode_icu.a"
    ],
    "linux": [
        "libskia.a", "libskottie.a", "libskshaper.a", "libsksg.a",
        "libskparagraph.a", "libsvg.a", "libskunicode_core.a",
        "libskunicode_libgrapheme.a" if USE_LIBGRAPHEME else "libskunicode_icu.a"
    ]
}

# Additional libraries for GPU variant (Dawn)
GPU_LIBS = {
    "mac": ["libdawn_combined.a"],
    "ios": [],  # iOS uses Metal directly
    "win": ["dawn_combined.lib"],
    "wasm": [],  # WASM uses browser WebGPU
    "linux": ["libdawn_combined.a"],
}

# Directories to package
PACKAGE_DIRS = [
    "include",
    "modules/skottie",
    "modules/skparagraph",
    "modules/skshaper",
    "modules/skresources",
    "modules/skunicode",
    "modules/skcms",
    "modules/svg",
    "src/core",
    "src/base",
    "src/utils",
    "src/xml",
    # Dawn headers for Graphite WebGPU backend
    "third_party/externals/dawn/include",
    # "third_party/externals/icu/source/common/unicode"
]

EXCLUDE_DEPS = [
    "third_party/externals/emsdk",
    "third_party/externals/v8",
    "third_party/externals/oboe",
    "third_party/externals/imgui",
    "third_party/externals/dng_sdk",
    "third_party/externals/microhttpd",
]

DONT_PACKAGE = [
    "android"
]

BASIC_GN_ARGS = """
cc = "clang"
cxx = "clang++"
"""

# Shared GN args
RELEASE_GN_ARGS = f"""
skia_use_system_libjpeg_turbo = false
skia_use_system_libpng = false
skia_use_system_zlib = false
skia_use_system_expat = false
skia_use_system_icu = false
skia_use_system_harfbuzz = false

skia_use_libwebp_decode = false
skia_use_libwebp_encode = false
skia_use_xps = false
skia_use_dng_sdk = false
skia_use_expat = true
skia_use_gl = true
skia_use_icu = {"false" if USE_LIBGRAPHEME else "true"}
skia_use_libgrapheme = {"true" if USE_LIBGRAPHEME else "false"}

skia_enable_graphite = true
skia_enable_svg = true
skia_enable_skottie = true
skia_enable_pdf = false
skia_enable_gpu = true
skia_enable_skparagraph = true
"""

# Platform-specific GN args
PLATFORM_GN_ARGS = {
    "mac": """
    skia_use_metal = true
    skia_use_dawn = true
    target_os = "mac"
    extra_cflags_c = ["-Wno-error"]
    """,

    "ios": f"""
    skia_use_metal = true
    target_os = "ios"
    skia_ios_use_signing = false
    extra_cflags = [
        "-miphoneos-version-min={IOS_MIN_VERSION}",
        "-I../../../src/skia/third_party/externals/expat/lib"
    ]
    extra_cflags_c = ["-Wno-error"]
    """,

    "win": """
    skia_use_dawn = true
    skia_use_direct3d = true
    is_trivial_abi = false
    """,

    "wasm": """
    target_os = "wasm"
    is_component_build = false
    is_trivial_abi = true
    werror = true
    skia_use_angle = false
    skia_use_dng_sdk = false
    skia_use_webgl = true
    skia_use_webgpu = true
    skia_use_expat = false
    skia_use_fontconfig = false
    skia_use_freetype = true
    skia_use_libheif = false
    skia_use_libjpeg_turbo_decode = true
    skia_use_libjpeg_turbo_encode = false
    skia_use_no_jpeg_encode = true
    skia_use_libpng_decode = true
    skia_use_libpng_encode = true
    skia_use_no_png_encode = false
    skia_use_libwebp_decode = true
    skia_use_libwebp_encode = false
    skia_use_no_webp_encode = true
    skia_use_lua = false
    skia_use_piex = false
    skia_use_system_freetype2 = false
    skia_use_system_libwebp = false
    skia_use_vulkan = false
    skia_use_wuffs = true
    skia_use_zlib = true
    skia_enable_ganesh = true
    skia_enable_graphite = false
    skia_build_for_debugger = false
    skia_enable_skottie = false
    skia_use_client_icu = false
    skia_use_icu4x = false
    skia_use_harfbuzz = true
    skia_use_system_harfbuzz = false
    skia_enable_fontmgr_custom_directory = false
    skia_enable_fontmgr_custom_embedded = true
    skia_enable_fontmgr_custom_empty = true
    skia_use_freetype_woff2 = true
    skia_enable_skshaper = true
    """,

    "linux": """
    skia_use_vulkan = true
    skia_use_dawn = true
    skia_use_x11 = true
    skia_use_fontconfig = true
    skia_use_freetype = true
    skia_use_system_freetype2 = false
    extra_cflags_c = ["-Wno-error"]
    """
}

# CPU-only GN args (disable all GPU backends)
CPU_ONLY_GN_ARGS = """
skia_enable_gpu = false
skia_enable_graphite = false
skia_use_gl = false
skia_use_vulkan = false
"""

# Platform-specific CPU-only GN args
PLATFORM_GN_ARGS_CPU = {
    "mac": """
    skia_use_metal = false
    skia_use_dawn = false
    target_os = "mac"
    extra_cflags_c = ["-Wno-error"]
    """,

    "ios": f"""
    skia_use_metal = false
    target_os = "ios"
    skia_ios_use_signing = false
    extra_cflags = [
        "-miphoneos-version-min={IOS_MIN_VERSION}",
        "-I../../../src/skia/third_party/externals/expat/lib"
    ]
    extra_cflags_c = ["-Wno-error"]
    """,

    "win": """
    skia_use_dawn = false
    skia_use_direct3d = false
    is_trivial_abi = false
    """,

    "wasm": """
    target_os = "wasm"
    is_component_build = false
    is_trivial_abi = true
    werror = true
    skia_use_angle = false
    skia_use_dng_sdk = false
    skia_use_webgl = false
    skia_use_webgpu = false
    skia_use_expat = false
    skia_use_fontconfig = false
    skia_use_freetype = true
    skia_use_libheif = false
    skia_use_libjpeg_turbo_decode = true
    skia_use_libjpeg_turbo_encode = false
    skia_use_no_jpeg_encode = true
    skia_use_libpng_decode = true
    skia_use_libpng_encode = true
    skia_use_no_png_encode = false
    skia_use_libwebp_decode = true
    skia_use_libwebp_encode = false
    skia_use_no_webp_encode = true
    skia_use_lua = false
    skia_use_piex = false
    skia_use_system_freetype2 = false
    skia_use_system_libwebp = false
    skia_use_vulkan = false
    skia_use_wuffs = true
    skia_use_zlib = true
    skia_enable_ganesh = false
    skia_enable_graphite = false
    skia_build_for_debugger = false
    skia_enable_skottie = false
    skia_use_client_icu = false
    skia_use_icu4x = false
    skia_use_harfbuzz = true
    skia_use_system_harfbuzz = false
    skia_enable_fontmgr_custom_directory = false
    skia_enable_fontmgr_custom_embedded = true
    skia_enable_fontmgr_custom_empty = true
    skia_use_freetype_woff2 = true
    skia_enable_skshaper = true
    """,

    "linux": """
    skia_use_vulkan = false
    skia_use_dawn = false
    skia_use_x11 = true
    skia_use_fontconfig = true
    skia_use_freetype = true
    skia_use_system_freetype2 = false
    extra_cflags_c = ["-Wno-error"]
    """
}

class SkiaBuildScript:
    def __init__(self):
        self.platform = None
        self.config = "Release"
        self.archs = []
        self.xcframework = False
        self.branch = None
        self.variant = "gpu"

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description="Build Skia for macOS, iOS, Windows, Linux and WebAssembly")
        parser.add_argument("platform", choices=["mac", "ios", "win", "linux", "wasm", "xcframework"],
                           help="Target platform or xcframework")
        parser.add_argument("-config", choices=["Debug", "Release"], default="Release", help="Build configuration")
        parser.add_argument("-archs", help="Target architectures (comma-separated)")
        parser.add_argument("-branch", help="Skia Git branch to checkout", default="main")
        parser.add_argument("-variant", choices=["cpu", "gpu"], default="gpu",
                           help="Build variant: cpu (no GPU) or gpu (with Graphite/Dawn)")
        parser.add_argument("--shallow", action="store_true", help="Perform a shallow clone of the Skia repository")
        parser.add_argument("--zip-all", action="store_true", 
                           help="Create a zip archive containing all platform libraries")
        args = parser.parse_args()

        if args.platform == "xcframework":
            self.xcframework = True
            self.platform = "mac"  # We'll handle iOS separately
            self.config = "Release"
            self.archs = ["universal"]
        else:
            self.platform = args.platform
            self.config = args.config
            if args.archs:
                self.archs = args.archs.split(',')
            else:
                self.archs = self.get_default_archs()

        self.branch = args.branch
        self.variant = args.variant
        self.shallow_clone = args.shallow
        self.create_zip_all = args.zip_all
        self.validate_archs()

    def get_default_archs(self):
        if self.platform == "mac":
            return ["universal"]
        elif self.platform == "ios":
            return ["x86_64", "arm64"]
        elif self.platform == "win":
            return ["x64"]
        elif self.platform == "linux":
            return ["x64"]
        elif self.platform == "wasm":
            return ["wasm32"]  # WebAssembly has only one architecture

    def validate_archs(self):
        valid_archs = {
            "mac": ["x86_64", "arm64", "universal"],
            "ios": ["x86_64", "arm64"],
            "win": ["x64", "Win32"],
            "linux": ["x64", "arm64"],
            "wasm": ["wasm32"]
        }
        for arch in self.archs:
            if arch not in valid_archs[self.platform]:
                colored_print(f"Invalid architecture for {self.platform}: {arch}", Colors.FAIL)
                sys.exit(1)

    def get_lib_dir(self, platform):
        """Get the library directory for a platform, including variant suffix."""
        variant_suffix = f"-{self.variant}"
        if platform == "mac":
            return BASE_DIR / f"mac{variant_suffix}" / "lib"
        elif platform == "ios":
            return BASE_DIR / f"ios{variant_suffix}" / "lib"
        elif platform == "wasm":
            return BASE_DIR / f"wasm{variant_suffix}" / "lib"
        elif platform == "linux":
            return BASE_DIR / f"linux{variant_suffix}" / "lib"
        else:  # Windows
            return BASE_DIR / f"win{variant_suffix}" / "lib"

    def setup_depot_tools(self):
        if not DEPOT_TOOLS_PATH.exists():
            subprocess.run(["git", "clone", DEPOT_TOOLS_URL, str(DEPOT_TOOLS_PATH)], check=True)
        os.environ["PATH"] = f"{DEPOT_TOOLS_PATH}:{os.environ['PATH']}"

    def sync_deps(self):
        os.chdir(SKIA_SRC_DIR)
        colored_print("Syncing Deps...", Colors.OKBLUE)
        subprocess.run(["python3", "tools/git-sync-deps"], check=True)

    def generate_gn_args(self, arch: str):
        output_dir = TMP_DIR / f"{self.platform}_{self.config}_{arch}_{self.variant}"
        gn_args = BASIC_GN_ARGS

        if self.config == 'Debug':
            gn_args += f"is_debug = true\n"
        else:
            # Use CPU or GPU platform-specific args based on variant
            if self.variant == "cpu":
                gn_args += PLATFORM_GN_ARGS_CPU[self.platform]
                gn_args += CPU_ONLY_GN_ARGS
            else:
                gn_args += PLATFORM_GN_ARGS[self.platform]
            gn_args += RELEASE_GN_ARGS
            gn_args += "is_debug = false\n"
            gn_args += "is_official_build = true\n"

        if self.platform == "mac":
            gn_args += f"target_cpu = \"{arch}\""
        elif self.platform == "ios":
            gn_args += f"target_cpu = \"{'arm64' if arch == 'arm64' else 'x64'}\""
        elif self.platform == "win":
            gn_args += f"extra_cflags = [\"{'/MTd' if self.config == 'Debug' else '/MT'}\"]\n"
            gn_args += f"target_cpu = \"{'x86' if arch == 'Win32' else 'x64'}\"\n"
            gn_args += "clang_win = \"C:\\Program Files\\LLVM\"\n"
        elif self.platform == "linux":
            gn_args += f"target_cpu = \"{'arm64' if arch == 'arm64' else 'x64'}\"\n"
        elif self.platform == "wasm":
            gn_args += "target_cpu = \"wasm\"\n"

        colored_print(f"Generating gn args for {self.platform} {arch} ({self.variant}) settings:", Colors.OKBLUE)
        colored_print(f"{gn_args}", Colors.OKGREEN)

        subprocess.run(["./bin/gn", "gen", str(output_dir), f"--args={gn_args}"], check=True)

    def build_skia(self, arch: str):
        output_dir = TMP_DIR / f"{self.platform}_{self.config}_{arch}_{self.variant}"
        
        # Get the list of libraries for the current platform
        libs_to_build = LIBS[self.platform]
        
        # On Windows, ninja expects targets without the .lib extension
        if self.platform == "win":
            libs_to_build = [lib[:-4] if lib.endswith('.lib') else lib for lib in libs_to_build]
        
        # Construct the ninja command with all library targets
        ninja_command = ["ninja", "-C", str(output_dir)] + libs_to_build

        # Run the ninja command
        try:
            subprocess.run(ninja_command, check=True)
            colored_print(f"Successfully built targets for {self.platform} {arch}", Colors.OKGREEN)
        except subprocess.CalledProcessError as e:
            colored_print(f"Error: Build failed for {self.platform} {arch}", Colors.FAIL)
            print(f"Ninja command: {' '.join(ninja_command)}")
            print(f"Error details: {e}")
            sys.exit(1)

    def move_libs(self, arch: str):
        src_dir = TMP_DIR / f"{self.platform}_{self.config}_{arch}_{self.variant}"
        lib_dir = self.get_lib_dir(self.platform)
        if self.platform == "mac":
            dest_dir = lib_dir / self.config / (arch if arch != "universal" else "")
        elif self.platform == "ios":
            dest_dir = lib_dir / self.config / arch
        elif self.platform == "wasm":
            dest_dir = lib_dir / self.config
        else:  # Windows, Linux
            dest_dir = lib_dir / self.config / arch

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy the libraries
        for lib in LIBS[self.platform]:
            src_file = src_dir / lib
            dest_file = dest_dir / lib
            if src_file.exists():
                shutil.copy2(str(src_file), str(dest_file))
                colored_print(f"Copied {lib} to {dest_dir}", Colors.OKGREEN)
                src_file.unlink()
            else:
                colored_print(f"Warning: {lib} not found in {src_dir}", Colors.WARNING)

        # Copy GPU-specific libraries (Dawn) for GPU variant
        if self.variant == "gpu" and self.platform in GPU_LIBS:
            for lib in GPU_LIBS[self.platform]:
                # Dawn combined library is in cmake_dawn subdirectory
                src_file = src_dir / "cmake_dawn" / lib
                if not src_file.exists():
                    # Try alternative location
                    src_file = src_dir / lib
                dest_file = dest_dir / lib
                if src_file.exists():
                    shutil.copy2(str(src_file), str(dest_file))
                    colored_print(f"Copied {lib} (Dawn) to {dest_dir}", Colors.OKGREEN)
                else:
                    colored_print(f"Warning: Dawn library {lib} not found", Colors.WARNING)

    # Lipo different architectures into a universal binary
    def create_universal_binary(self):
        colored_print('Creating universal files...', Colors.OKBLUE)
        lib_dir = self.get_lib_dir("mac")
        dest_dir = lib_dir / self.config
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Combine Skia libraries
        for lib in LIBS[self.platform]:
            input_libs = [str(lib_dir / self.config / arch / lib) for arch in ["x86_64", "arm64"]]
            output_lib = str(dest_dir / lib)
            subprocess.run(["lipo", "-create"] + input_libs + ["-output", output_lib], check=True)
            colored_print(f"Created universal file: {lib}", Colors.OKGREEN)

        # Combine Dawn libraries for GPU variant
        if self.variant == "gpu" and "mac" in GPU_LIBS:
            for lib in GPU_LIBS["mac"]:
                input_libs = []
                for arch in ["x86_64", "arm64"]:
                    lib_path = lib_dir / self.config / arch / lib
                    if lib_path.exists():
                        input_libs.append(str(lib_path))
                if len(input_libs) == 2:
                    output_lib = str(dest_dir / lib)
                    subprocess.run(["lipo", "-create"] + input_libs + ["-output", output_lib], check=True)
                    colored_print(f"Created universal file: {lib} (Dawn)", Colors.OKGREEN)
                elif len(input_libs) == 1:
                    # Only one arch available, just copy it
                    shutil.copy2(input_libs[0], str(dest_dir / lib))
                    colored_print(f"Copied single-arch file: {lib} (Dawn)", Colors.WARNING)

        # Remove architecture-specific folders
        shutil.rmtree(lib_dir / self.config / "x86_64", ignore_errors=True)
        shutil.rmtree(lib_dir / self.config / "arm64", ignore_errors=True)

    # Combine the various skia libraries into a single static library for each platform
    def combine_libraries(self, platform, arch):
        colored_print(f"Combining libraries for {platform} {arch}...", Colors.OKBLUE)
        base_lib_dir = self.get_lib_dir(platform)
        if platform == "mac":
            lib_dir = base_lib_dir / self.config / (arch if arch != "universal" else "")
        else:  # iOS
            lib_dir = base_lib_dir / self.config / arch

        output_lib = lib_dir / "libSkia.a"
        input_libs = [str(lib_dir / lib) for lib in LIBS[platform] if (lib_dir / lib).exists()]

        if input_libs:
            libtool_command = ["libtool", "-static", "-o", str(output_lib)] + input_libs
            subprocess.run(libtool_command, check=True)
            colored_print(f"Created combined library: {output_lib}", Colors.OKGREEN)
        else:
            colored_print(f"No libraries found to combine for {platform} {arch}", Colors.WARNING)

    def create_xcframework(self, with_headers=False):
        colored_print("Creating Skia XCFramework...", Colors.OKBLUE)
        xcframework_dir = BASE_DIR / "xcframework"
        xcframework_dir.mkdir(parents=True, exist_ok=True)

        xcframework_path = xcframework_dir / "Skia.xcframework"

        # Remove existing XCFramework if it exists
        if xcframework_path.exists():
            shutil.rmtree(xcframework_path)

        xcframework_command = ["xcodebuild", "-create-xcframework"]

        # Add iOS libraries
        ios_lib_dir = self.get_lib_dir("ios")
        for ios_arch in ["x86_64", "arm64"]:
            ios_lib_path = ios_lib_dir / "Release" / ios_arch / "libSkia.a"
            xcframework_command.extend(["-library", str(ios_lib_path)])
            # Add headers
            if with_headers:
                headers_path = BASE_DIR / "include"
                xcframework_command.extend(["-headers", str(headers_path)])

        # Add macOS universal library
        mac_lib_dir = self.get_lib_dir("mac")
        mac_lib_path = mac_lib_dir / "Release" / "libSkia.a"
        xcframework_command.extend(["-library", str(mac_lib_path)])

        # Add headers
        if with_headers:
            headers_path = BASE_DIR / "include"
            xcframework_command.extend(["-headers", str(headers_path)])

        # Specify output
        xcframework_command.extend(["-output", str(xcframework_path)])

        try:
            subprocess.run(xcframework_command, check=True)
            colored_print(f"Created Skia XCFramework at {xcframework_path}", Colors.OKGREEN)
        except subprocess.CalledProcessError as e:
            colored_print(f"Error creating Skia XCFramework", Colors.FAIL)
            print(f"Command: {' '.join(xcframework_command)}")
            print(f"Error details: {e}")


    def package_headers(self, dest_dir):
        colored_print(f"Packaging headers to {dest_dir}...", Colors.OKBLUE)
        dest_dir.mkdir(parents=True, exist_ok=True)

        for dir_path in PACKAGE_DIRS:
            src_path = SKIA_SRC_DIR / dir_path
            if src_path.exists() and src_path.is_dir():
                for root, dirs, files in os.walk(src_path):
                    # Remove excluded directories
                    dirs[:] = [d for d in dirs if d not in DONT_PACKAGE]

                    for file in files:
                        if file.endswith('.h'):
                            src_file = Path(root) / file
                            rel_path = src_file.relative_to(SKIA_SRC_DIR)

                            # Check if the file is in an excluded directory
                            if not any(exclude in rel_path.parts for exclude in DONT_PACKAGE):
                                dest_file = dest_dir / rel_path
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src_file, dest_file)
                                # print(f"Copied {rel_path} to {dest_file}")

    def package_generated_dawn_headers(self, build_dir, dest_dir):
        """Copy generated Dawn headers from build output to package."""
        gen_include_dir = build_dir / "gen" / "third_party" / "dawn" / "include"

        # Copy dawn/*.h (webgpu.h, webgpu_cpp.h, etc.)
        gen_dawn_dir = gen_include_dir / "dawn"
        if gen_dawn_dir.exists():
            colored_print(f"Packaging generated Dawn headers from {gen_dawn_dir}...", Colors.OKBLUE)
            dest_dawn_dir = dest_dir / "dawn"
            dest_dawn_dir.mkdir(parents=True, exist_ok=True)
            for file in gen_dawn_dir.glob("*.h"):
                shutil.copy2(file, dest_dawn_dir / file.name)
                colored_print(f"  Copied dawn/{file.name}", Colors.OKCYAN)
        else:
            colored_print(f"Warning: Generated Dawn headers not found at {gen_dawn_dir}", Colors.WARNING)

        # Copy webgpu/*.h (webgpu_cpp_chained_struct.h, etc.)
        gen_webgpu_dir = gen_include_dir / "webgpu"
        if gen_webgpu_dir.exists():
            colored_print(f"Packaging generated WebGPU headers from {gen_webgpu_dir}...", Colors.OKBLUE)
            dest_webgpu_dir = dest_dir / "webgpu"
            dest_webgpu_dir.mkdir(parents=True, exist_ok=True)
            for file in gen_webgpu_dir.glob("*.h"):
                shutil.copy2(file, dest_webgpu_dir / file.name)
                colored_print(f"  Copied webgpu/{file.name}", Colors.OKCYAN)


#     def create_swift_package(self):
#         colored_print("Creating Swift package...", Colors.OKBLUE)
#         package_dir = BASE_DIR / "spm" / "Skia"
#         package_dir.mkdir(parents=True, exist_ok=True)

#         # Create package structure
#         (package_dir / "Sources" / "Skia").mkdir(parents=True, exist_ok=True)
#         (package_dir / "Skia").mkdir(parents=True, exist_ok=True)

#         # Move XCFramework
#         xcframework_src = BASE_DIR / "xcframework" / "Skia.xcframework"
#         xcframework_dest = package_dir / "Skia" / "Skia.xcframework"
#         if xcframework_src.exists():
#             if xcframework_dest.exists():
#                 shutil.rmtree(xcframework_dest)
#             shutil.copytree(xcframework_src, xcframework_dest)
#             colored_print(f"Copied XCFramework to {xcframework_dest}", Colors.OKGREEN)
#         else:
#             colored_print(f"Warning: XCFramework not found at {xcframework_src}", Colors.WARNING)

#         # Copy headers
#         headers_dest = package_dir / "Sources" / "Skia"
#         self.package_headers(headers_dest)

#         # Create dummy.cpp
#         with open(package_dir / "Sources" / "Skia" / "dummy.cpp", "w") as f:
#             f.write("// This file is needed to make SPM happy\n")

#         # Create Package.swift
#         package_swift_content = """
# // swift-tools-version:5.3
# import PackageDescription

# let package = Package(
#     name: "Skia",
#     products: [
#         .library(
#             name: "Skia",
#             targets: ["Skia", "SkiaXCFramework"])
#     ],
#     targets: [
#         .target(
#             name: "Skia",
#             dependencies: ["SkiaXCFramework"],
#             path: "Sources",
#             publicHeadersPath: "Skia"),
#         .binaryTarget(
#             name: "SkiaXCFramework",
#             path: "Skia/Skia.xcframework"),
#     ],
#     cxxLanguageStandard: .cxx14
# )
#         """
#         with open(package_dir / "Package.swift", "w") as f:
#             f.write(package_swift_content)

#         colored_print(f"Swift package created at {package_dir}", Colors.OKGREEN)
    

    def cleanup(self):
        for arch in self.archs:
            shutil.rmtree(TMP_DIR / f"{self.platform}_{self.config}_{arch}_{self.variant}", ignore_errors=True)
        colored_print("Cleaned up temporary directories", Colors.OKBLUE)

    def setup_skia_repo(self):
        colored_print(f"Setting up Skia repository (branch: {self.branch})...", Colors.OKBLUE)
        if not SKIA_SRC_DIR.exists():
            clone_command = ["git", "clone"]
            if self.shallow_clone:
                clone_command.extend(["--depth", "1"])
            clone_command.extend(["--branch", self.branch, SKIA_GIT_URL, str(SKIA_SRC_DIR)])
            subprocess.run(clone_command, check=True)
        else:
            os.chdir(SKIA_SRC_DIR)
            fetch_command = ["git", "fetch"]
            if self.shallow_clone:
                fetch_command.extend(["--depth", "1"])
            fetch_command.extend(["origin", self.branch])
            subprocess.run(fetch_command, check=True)
            subprocess.run(["git", "checkout", self.branch], check=True)
            subprocess.run(["git", "reset", "--hard", f"origin/{self.branch}"], check=True)
        colored_print("Skia repository setup complete.", Colors.OKGREEN)
    
    def generate_gn_args_summary(self, arch: str):
        if self.variant == "cpu":
            gn_args = BASIC_GN_ARGS + PLATFORM_GN_ARGS_CPU[self.platform] + CPU_ONLY_GN_ARGS
        else:
            gn_args = BASIC_GN_ARGS + PLATFORM_GN_ARGS[self.platform]
        gn_args += RELEASE_GN_ARGS
        gn_args += f"""
        is_debug = {"true" if self.config == 'Debug' else "false"}
        is_official_build = {"false" if self.config == 'Debug' else "true"}
        target_cpu = "{arch}"
        variant = "{self.variant}"
        """
        return gn_args.strip()

    def write_gn_args_summary(self):
        lib_dir = self.get_lib_dir(self.platform)
        if self.platform == "wasm":
            summary_file = lib_dir.parent / "gn_args.txt"
        else:
            summary_file = lib_dir / "gn_args.txt"

        summary_file.parent.mkdir(parents=True, exist_ok=True)

        with open(summary_file, "w") as f:
            f.write(f"Skia Build Summary for {self.platform} ({self.variant})\n")
            f.write(f"Configuration: {self.config}\n")
            f.write(f"Variant: {self.variant}\n")
            f.write(f"Architectures: {', '.join(self.archs)}\n\n")
            f.write("GN Arguments:\n")
            for arch in self.archs:
                f.write(f"\nFor {arch}:\n")
                f.write(self.generate_gn_args_summary(arch))
                f.write("\n")
        colored_print(f"GN args summary written to {summary_file}", Colors.OKGREEN)

    def modify_deps(self):
        deps_path = SKIA_SRC_DIR / "DEPS"
        if not deps_path.exists():
            colored_print(f"Error: {deps_path} not found.", Colors.FAIL)
            sys.exit(1)

        with open(deps_path, "r") as file:
            lines = file.readlines()

        with open(deps_path, "w") as file:
            for line in lines:
                if not any(exclude in line for exclude in EXCLUDE_DEPS):
                    file.write(line)
                else:
                    file.write(f"# {line}")

        colored_print(f"Modified {deps_path} to exclude specified dependencies.", Colors.OKGREEN)

    def patch_activate_emsdk(self):
        if not ACTIVATE_EMSDK_PATH.exists():
            colored_print(f"Error: {ACTIVATE_EMSDK_PATH} not found.", Colors.FAIL)
            sys.exit(1)

        with open(ACTIVATE_EMSDK_PATH, "r") as file:
            lines = file.readlines()

        with open(ACTIVATE_EMSDK_PATH, "w") as file:
            for line in lines:
                file.write(line)
                if line.strip() == "def main():":
                    file.write("    return\n")

        colored_print(f"Patched {ACTIVATE_EMSDK_PATH} to prevent emscripten downloading.", Colors.OKGREEN)

    def run(self):
        self.parse_arguments()
        self.setup_depot_tools()
        self.setup_skia_repo()

        # if self.config == "Release":
        #     self.modify_deps()
        
        # self.patch_activate_emsdk()

        self.sync_deps()

        if "universal" in self.archs or self.xcframework:
            self.archs = ["x86_64", "arm64"]

        for arch in self.archs:
            self.generate_gn_args(arch)
            self.build_skia(arch)
            self.move_libs(arch)

        if self.platform == "mac" and self.archs == ["x86_64", "arm64"]:
            self.create_universal_binary()

        if self.xcframework:
            # Build for macOS
            self.combine_libraries("mac", "universal")

            # Build for iOS
            self.platform = "ios"
            self.archs = ["x86_64", "arm64"]
            for arch in self.archs:
                self.generate_gn_args(arch)
                self.build_skia(arch)
                self.move_libs(arch)
                self.combine_libraries("ios", arch)

            self.package_headers(BASE_DIR / "include")
            self.create_xcframework(with_headers=True)
        else:
            self.package_headers(BASE_DIR / "include")

        # Copy generated Dawn headers (for Graphite WebGPU backend)
        if self.variant == "gpu":
            # Use the first arch's build dir for generated headers (they're the same across archs)
            first_arch = self.archs[0]
            build_dir = TMP_DIR / f"{self.platform}_{self.config}_{first_arch}_{self.variant}"
            self.package_generated_dawn_headers(build_dir, BASE_DIR / "include")

        self.write_gn_args_summary()

        colored_print(f"Build completed successfully for {self.platform} {self.config} configuration with architectures: {', '.join(self.archs)}", Colors.OKGREEN)
        if hasattr(self, 'create_zip_all') and self.create_zip_all:
            self.create_all_platforms_zip()
        
        colored_print(f"Build completed successfully for {self.platform} {self.config} "
                     f"configuration with architectures: {', '.join(self.archs)}", 
                     Colors.OKGREEN)

    def create_all_platforms_zip(self):
        """Create a zip file containing headers and libraries for all platforms."""
        colored_print("Creating zip archive with all platforms...", Colors.OKBLUE)

        zip_path = BASE_DIR / f"skia-all-platforms-{self.variant}.zip"
        include_dir = BASE_DIR / "include"

        if not include_dir.exists():
            colored_print("Error: Include directory not found", Colors.FAIL)
            return

        try:
            import zipfile
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add include directory
                for root, _, files in os.walk(include_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(BASE_DIR)
                        zipf.write(file_path, arcname)

                # Add all platform lib directories for current variant
                for platform in ["mac", "ios", "win", "linux", "wasm"]:
                    lib_dir = self.get_lib_dir(platform)
                    if lib_dir.exists():
                        for root, _, files in os.walk(lib_dir):
                            for file in files:
                                file_path = Path(root) / file
                                arcname = file_path.relative_to(BASE_DIR)
                                zipf.write(file_path, arcname)
                    else:
                        colored_print(f"Warning: {platform} library directory not found",
                                    Colors.WARNING)

            colored_print(f"Created zip archive at {zip_path}", Colors.OKGREEN)
        except Exception as e:
            colored_print(f"Error creating zip archive: {e}", Colors.FAIL)
if __name__ == "__main__":
    SkiaBuildScript().run()
