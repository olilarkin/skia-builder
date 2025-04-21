#!/usr/bin/env python3

"""
build-skia.py

This script automates the process of building Skia libraries for various platforms
(macOS, iOS, and Windows). It handles the setup of the build environment, cloning
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
    ]
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
    "mac": f"""
    skia_use_metal = true
    skia_use_dawn = true
    target_os = "mac"
    extra_cflags = ["-mmacosx-version-min={MAC_MIN_VERSION}"]
    extra_asmflags = ["-mmacosx-version-min={MAC_MIN_VERSION}"]
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
    """
}

class SkiaBuildScript:
    def __init__(self):
        self.platform = None
        self.config = "Release"
        self.archs = []
        self.xcframework = False
        self.branch = None

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description="Build Skia for macOS, iOS, Windows and WebAssembly")
        parser.add_argument("platform", choices=["mac", "ios", "win", "wasm", "xcframework"], 
                           help="Target platform or xcframework")
        parser.add_argument("-config", choices=["Debug", "Release"], default="Release", help="Build configuration")
        parser.add_argument("-archs", help="Target architectures (comma-separated)")
        parser.add_argument("-branch", help="Skia Git branch to checkout", default="main")
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
        self.shallow_clone = args.shallow
        self.create_zip_all = args.zip_all
        self.validate_archs()

    def get_default_archs(self):
        if self.platform == "mac":
            return ["universal"]
        elif self.platform == "ios":
            return ["x86_64", "arm64"]
        elif self.platform == "win":
            # On Windows ARM64 machine, default to arm64 target
            if self.is_arm64_host():
                return ["arm64"]
            return ["x64"]
        elif self.platform == "wasm":
            return ["wasm32"]  # WebAssembly has only one architecture

    def validate_archs(self):
        valid_archs = {
            "mac": ["x86_64", "arm64", "universal"],
            "ios": ["x86_64", "arm64"],
            "win": ["x64", "Win32", "arm64"],
            "wasm": ["wasm32"]
        }
        for arch in self.archs:
            if arch not in valid_archs[self.platform]:
                colored_print(f"Invalid architecture for {self.platform}: {arch}", Colors.FAIL)
                sys.exit(1)

    def setup_depot_tools(self):
        if not DEPOT_TOOLS_PATH.exists():
            subprocess.run(["git", "clone", DEPOT_TOOLS_URL, str(DEPOT_TOOLS_PATH)], check=True)
        
        # Properly format the PATH separator based on platform
        path_separator = ";" if sys.platform.startswith('win') else ":"
        os.environ["PATH"] = f"{DEPOT_TOOLS_PATH}{path_separator}{os.environ['PATH']}"
        
        # On Windows, tell depot_tools to use 'python' instead of 'python3'
        if sys.platform.startswith('win'):
            os.environ["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"
            os.environ["PYTHONPATH"] = str(DEPOT_TOOLS_PATH)
            # Set GN to use python instead of python3
            os.environ["PYTHON_BIN"] = "python"

    def sync_deps(self):
        os.chdir(SKIA_SRC_DIR)
        colored_print("Syncing Deps...", Colors.OKBLUE)
        
        # Disable emsdk setup before syncing deps
        # It will be installed but not activated to save time and avoid errors
        self.patch_activate_emsdk()
        
        # Check if we're on Windows
        if sys.platform.startswith('win'):
            # Set environment variables to prevent emsdk activation problems
            os.environ["EMSDK_NOTTY"] = "1"  # Prevent TTY detection
            os.environ["EMSDK"] = "0"        # Disable emsdk
            # Use 'python' or 'py' on Windows
            subprocess.run(["python", "tools/git-sync-deps"], check=True)
        else:
            # Use 'python3' on macOS/Linux
            subprocess.run(["python3", "tools/git-sync-deps"], check=True)

    def is_arm64_host(self):
        """Detect if we're running on an ARM64 host."""
        if sys.platform.startswith('win'):
            # Check for ARM64 in environment variables
            if "CLANGARM64" in os.environ.get("MSYSTEM", ""):
                return True
            
            # Try to detect ARM64 using Windows-specific methods
            try:
                # Try using the PROCESSOR_ARCHITECTURE environment variable
                if os.environ.get("PROCESSOR_ARCHITECTURE", "").lower() == "arm64":
                    return True
                
                # Try detecting using PowerShell if available
                result = subprocess.run(
                    ["powershell", "-Command", "(Get-WmiObject Win32_Processor).Architecture -eq 12"],
                    capture_output=True, text=True, check=False
                )
                if result.stdout.strip().lower() == "true":
                    return True
            except Exception:
                pass
        
        # For non-Windows platforms or if detection failed
        return False

    def generate_gn_args(self, arch: str):
        output_dir = TMP_DIR / f"{self.platform}_{self.config}_{arch}"
        gn_args = BASIC_GN_ARGS

        if self.config == 'Debug':
            gn_args += f"is_debug = true\n"
        else:
            gn_args += PLATFORM_GN_ARGS[self.platform]
            gn_args += RELEASE_GN_ARGS
            gn_args += "is_debug = false\n"
            gn_args += "is_official_build = true\n"

        # Check if running on ARM64 host
        is_arm64 = self.is_arm64_host()
        
        if self.platform == "mac":
            gn_args += f"target_cpu = \"{arch}\""
        elif self.platform == "ios":
            gn_args += f"target_cpu = \"{'arm64' if arch == 'arm64' else 'x64'}\""
        elif self.platform == "win":
            gn_args += f"extra_cflags = [\"{'/MTd' if self.config == 'Debug' else '/MT'}\"]\n"
            
            if arch == "arm64":
                gn_args += "target_cpu = \"arm64\"\n"
                # For ARM64 Windows builds
                gn_args += "skia_use_sse2 = false\n"
                gn_args += "skia_use_sse3 = false\n"
                gn_args += "skia_use_ssse3 = false\n"
                gn_args += "skia_use_sse41 = false\n"
                gn_args += "skia_use_sse42 = false\n"
                gn_args += "skia_use_avx = false\n"
                gn_args += "skia_use_avx2 = false\n"
            else:
                gn_args += f"target_cpu = \"{'x86' if arch == 'Win32' else 'x64'}\"\n"
                
                # If building x64 on ARM64, disable CPU-specific optimizations
                if is_arm64 and arch != "arm64":
                    colored_print("ARM64 host detected. Disabling x86-specific CPU optimizations...", Colors.WARNING)
                    gn_args += "skia_enable_ssse3 = false\n"
                    gn_args += "skia_enable_sse42 = false\n"
                    gn_args += "skia_enable_avx = false\n"
                    gn_args += "skia_enable_avx2 = false\n"
                    gn_args += "skia_enable_hsw = false\n"
                    gn_args += "skia_enable_f16c = false\n"
                    gn_args += "skia_enable_popcnt = false\n"
                    
            gn_args += "clang_win = \"C:\\\\Program Files\\\\LLVM\"\n"
        elif self.platform == "wasm":
            gn_args += "target_cpu = \"wasm\"\n"

        colored_print(f"Generating gn args for {self.platform} {arch} settings:", Colors.OKBLUE)
        colored_print(f"{gn_args}", Colors.OKGREEN)

        # Use platform-specific path to gn
        if sys.platform.startswith('win'):
            gn_path = SKIA_SRC_DIR / "bin" / "gn.exe"
        else:
            gn_path = "./bin/gn"
        
        if not Path(gn_path).exists():
            colored_print(f"Error: gn executable not found at {gn_path}", Colors.FAIL)
            gn_dir = SKIA_SRC_DIR / "bin"
            if gn_dir.exists():
                colored_print(f"Contents of {gn_dir}:", Colors.WARNING)
                for file in gn_dir.iterdir():
                    colored_print(f"  {file.name}", Colors.WARNING)
            sys.exit(1)
            
        # Print environment info for debugging
        colored_print("Environment information:", Colors.OKBLUE)
        colored_print(f"  PATH: {os.environ.get('PATH', '')}", Colors.OKGREEN)
        colored_print(f"  PYTHON_BIN: {os.environ.get('PYTHON_BIN', 'Not set')}", Colors.OKGREEN)
        colored_print(f"  PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}", Colors.OKGREEN)
        colored_print(f"  Running on ARM64: {is_arm64}", Colors.OKGREEN)
        
        try:
            result = subprocess.run([str(gn_path), "gen", str(output_dir), f"--args={gn_args}"], 
                                   check=False, capture_output=True, text=True)
            if result.returncode != 0:
                colored_print(f"Error running gn gen:", Colors.FAIL)
                colored_print(f"Return code: {result.returncode}", Colors.FAIL)
                colored_print(f"stdout: {result.stdout}", Colors.WARNING)
                colored_print(f"stderr: {result.stderr}", Colors.WARNING)
                sys.exit(1)
            colored_print("GN gen completed successfully", Colors.OKGREEN)
        except Exception as e:
            colored_print(f"Exception running gn gen: {e}", Colors.FAIL)
            sys.exit(1)

    def build_skia(self, arch: str):
        output_dir = TMP_DIR / f"{self.platform}_{self.config}_{arch}"
        
        # Get the list of libraries for the current platform
        libs_to_build = LIBS[self.platform]
        
        # On Windows, ninja expects targets without the .lib extension
        if self.platform == "win":
            libs_to_build = [lib[:-4] if lib.endswith('.lib') else lib for lib in libs_to_build]
        
        # Find the ninja executable
        if sys.platform.startswith('win'):
            # Look for ninja in depot_tools
            ninja_path = DEPOT_TOOLS_PATH / "ninja.exe"
            if not ninja_path.exists():
                # Try to find it in subfolders
                for root, dirs, files in os.walk(DEPOT_TOOLS_PATH):
                    if "ninja.exe" in files:
                        ninja_path = Path(root) / "ninja.exe"
                        break
            
            if not ninja_path.exists():
                colored_print("Ninja not found in depot_tools, downloading it...", Colors.WARNING)
                # Download ninja from GitHub releases
                import urllib.request
                import zipfile
                
                ninja_zip = TMP_DIR / "ninja.zip"
                ninja_url = "https://github.com/ninja-build/ninja/releases/download/v1.11.1/ninja-win.zip"
                
                colored_print(f"Downloading ninja from {ninja_url}...", Colors.OKBLUE)
                urllib.request.urlretrieve(ninja_url, ninja_zip)
                
                # Extract to temp directory
                with zipfile.ZipFile(ninja_zip, 'r') as zip_ref:
                    zip_ref.extractall(TMP_DIR)
                
                ninja_path = TMP_DIR / "ninja.exe"
                colored_print(f"Ninja extracted to {ninja_path}", Colors.OKGREEN)
                
            colored_print(f"Using ninja at: {ninja_path}", Colors.OKGREEN)
            ninja_command = [str(ninja_path), "-C", str(output_dir)] + libs_to_build
        else:
            # On non-Windows platforms, ninja should be in the PATH from depot_tools
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
        src_dir = TMP_DIR / f"{self.platform}_{self.config}_{arch}"
        if self.platform == "mac":
            dest_dir = MAC_LIB_DIR / self.config / (arch if arch != "universal" else "")
        elif self.platform == "ios":
            dest_dir = IOS_LIB_DIR / self.config / arch
        elif self.platform == "wasm":
            dest_dir = WASM_LIB_DIR / self.config
        else:  # Windows
            dest_dir = WIN_LIB_DIR / self.config / arch

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

    # Lipo different architectures into a universal binary
    def create_universal_binary(self):
        colored_print('Creating universal files...', Colors.OKBLUE)
        dest_dir = MAC_LIB_DIR / self.config
        dest_dir.mkdir(parents=True, exist_ok=True)

        for lib in LIBS[self.platform]:
            input_libs = [str(MAC_LIB_DIR / self.config / arch / lib) for arch in ["x86_64", "arm64"]]
            output_lib = str(dest_dir / lib)
            subprocess.run(["lipo", "-create"] + input_libs + ["-output", output_lib], check=True)
            colored_print(f"Created universal file: {lib}", Colors.OKGREEN)

        # Remove architecture-specific folders
        shutil.rmtree(MAC_LIB_DIR / self.config / "x86_64", ignore_errors=True)
        shutil.rmtree(MAC_LIB_DIR / self.config / "arm64", ignore_errors=True)

    # Combine the various skia libraries into a single static library for each platform
    def combine_libraries(self, platform, arch):
        colored_print(f"Combining libraries for {platform} {arch}...", Colors.OKBLUE)
        if platform == "mac":
            lib_dir = MAC_LIB_DIR / self.config / (arch if arch != "universal" else "")
        else:  # iOS
            lib_dir = IOS_LIB_DIR / self.config / arch

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
        for ios_arch in ["x86_64", "arm64"]:
            ios_lib_path = IOS_LIB_DIR / "Release" / ios_arch / "libSkia.a"
            xcframework_command.extend(["-library", str(ios_lib_path)])
            # Add headers
            if with_headers:
                headers_path = BASE_DIR / "include"
                xcframework_command.extend(["-headers", str(headers_path)])

        # Add macOS universal library
        mac_lib_path = MAC_LIB_DIR / "Release" / "libSkia.a"
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
            shutil.rmtree(TMP_DIR / f"{self.platform}_{self.config}_{arch}", ignore_errors=True)
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
        gn_args = BASIC_GN_ARGS + PLATFORM_GN_ARGS[self.platform] + RELEASE_GN_ARGS
        gn_args += f"""
        is_debug = {"true" if self.config == 'Debug' else "false"}
        is_official_build = {"false" if self.config == 'Debug' else "true"}
        target_cpu = "{arch}"
        """
        return gn_args.strip()

    def write_gn_args_summary(self):
        if self.platform == "mac":
            summary_file = MAC_LIB_DIR / "gn_args.txt"
        elif self.platform == "ios":
            summary_file = IOS_LIB_DIR / "gn_args.txt"
        elif self.platform == "wasm":
            summary_file = BASE_DIR / "wasm" / "gn_args.txt"
        else:  # Windows
            summary_file = WIN_LIB_DIR / "gn_args.txt"

        summary_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(summary_file, "w") as f:
            f.write(f"Skia Build Summary for {self.platform}\n")
            f.write(f"Configuration: {self.config}\n")
            f.write(f"Architectures: {', '.join(self.archs)}\n\n")
            f.write("GN Arguments:\n")
            for arch in self.archs:
                f.write(f"\nFor {arch}:\n")
                f.write(self.generate_gn_args_summary(arch))
                f.write("\n")
        colored_print(f"GN args summary written to {summary_file}", Colors.OKGREEN)

    def modify_deps(self):
        """Modify the DEPS file to exclude certain dependencies."""
        deps_path = SKIA_SRC_DIR / "DEPS"
        if not deps_path.exists():
            colored_print(f"Error: {deps_path} not found.", Colors.FAIL)
            sys.exit(1)

        try:
            with open(deps_path, "r") as file:
                lines = file.readlines()

            with open(deps_path, "w") as file:
                for line in lines:
                    if not any(exclude in line for exclude in EXCLUDE_DEPS):
                        file.write(line)
                    else:
                        file.write(f"# {line}")

            colored_print(f"Modified {deps_path} to exclude specified dependencies.", Colors.OKGREEN)
        except Exception as e:
            colored_print(f"Error modifying DEPS file: {e}", Colors.FAIL)

    def patch_activate_emsdk(self):
        """Modify the activate-emsdk script to prevent it from running emscripten setup."""
        colored_print("Patching activate-emsdk script...", Colors.OKBLUE)
        
        # Path to the activate-emsdk script
        activate_path = SKIA_SRC_DIR / "bin" / "activate-emsdk"
        
        if not activate_path.exists():
            colored_print(f"Warning: {activate_path} not found, creating a dummy version", Colors.WARNING)
            activate_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(activate_path, "w") as f:
                f.write("#!/usr/bin/env python\n\n")
                f.write("def main():\n")
                f.write("    return\n\n")
                f.write("if __name__ == '__main__':\n")
                f.write("    main()\n")
            
            colored_print(f"Created dummy activate-emsdk script", Colors.OKGREEN)
            return
            
        # If the file exists, modify it
        try:
            with open(activate_path, "r") as f:
                content = f.read()
                
            # Simple patch: make the main function return immediately
            if "def main():" in content:
                content = content.replace("def main():", "def main():\n    return  # Patched to skip emsdk activation")
                
                with open(activate_path, "w") as f:
                    f.write(content)
                    
                colored_print(f"Successfully patched {activate_path}", Colors.OKGREEN)
            else:
                colored_print(f"Warning: Could not patch {activate_path}, unexpected content", Colors.WARNING)
                
        except Exception as e:
            colored_print(f"Error patching activate-emsdk: {e}", Colors.FAIL)
            
    def setup_python3_on_windows(self):
        """Create a python3.bat file in the PATH to redirect python3 calls to python on Windows."""
        if not sys.platform.startswith('win'):
            return
            
        colored_print("Setting up python3 wrapper for Windows...", Colors.OKBLUE)
        
        # Create a batch file that redirects python3 to python
        temp_dir = BASE_DIR / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        python3_bat = temp_dir / "python3.bat"
        with open(python3_bat, "w") as f:
            f.write('@echo off\r\n')
            f.write('python %*\r\n')
        
        # Add the directory containing the batch file to the PATH
        os.environ["PATH"] = f"{temp_dir};{os.environ['PATH']}"
        colored_print(f"Created python3 wrapper at {python3_bat}", Colors.OKGREEN)

    def run(self):
        self.parse_arguments()
        self.setup_depot_tools()
        
        # Set up python3 wrapper on Windows
        if sys.platform.startswith('win'):
            self.setup_python3_on_windows()
            
        self.setup_skia_repo()

        # For Release builds, modify DEPS to exclude unnecessary dependencies
        if self.config == "Release":
            self.modify_deps()

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
        
        zip_path = BASE_DIR / "skia-all-platforms.zip"
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
                
                # Add all platform lib directories
                platform_dirs = {
                    "mac": MAC_LIB_DIR,
                    "ios": IOS_LIB_DIR,
                    "win": WIN_LIB_DIR,
                    "wasm": WASM_LIB_DIR
                }
                
                for platform, lib_dir in platform_dirs.items():
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
