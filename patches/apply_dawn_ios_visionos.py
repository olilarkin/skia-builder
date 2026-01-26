#!/usr/bin/env python3
"""
Apply Dawn iOS/visionOS support patches.

This script modifies Dawn's build files to support iOS and visionOS builds.
It's used instead of a .patch file because git diff format has issues with
empty context lines.
"""

import sys
from pathlib import Path

def apply_patches(skia_dir: Path):
    """Apply all Dawn iOS/visionOS patches."""
    dawn_dir = skia_dir / "third_party" / "dawn"

    # 1. Modify args.gni - add dawn_target_platform
    args_gni = dawn_dir / "args.gni"
    content = args_gni.read_text()

    if "dawn_target_platform" not in content:
        new_content = content.replace(
            '  dawn_enable_vulkan = is_linux || is_android\n}',
            '''  dawn_enable_vulkan = is_linux || is_android

  # Target platform override for visionOS builds (which use target_os=ios as a workaround)
  # Set to "visionos" when building for visionOS, otherwise leave as empty string
  dawn_target_platform = ""
}'''
        )
        args_gni.write_text(new_content)
        print("  Patched args.gni")
    else:
        print("  args.gni already patched")

    # 2. Modify BUILD.gn - add iOS/visionOS flags
    build_gn = dawn_dir / "BUILD.gn"
    content = build_gn.read_text()

    if "--ios_simulator" not in content:
        insertion = '''
  # Pass iOS simulator flag to CMake (iOS only)
  # This is needed because on Apple Silicon, arm64 is used for both device
  # and simulator builds, so we can't infer simulator from CPU architecture.
  if (is_ios && defined(ios_use_simulator) && ios_use_simulator) {
    args += [ "--ios_simulator" ]
  }

  # Pass visionOS target platform to CMake (for visionOS builds using target_os=ios workaround)
  # When dawn_target_platform="visionos", Dawn will use xros SDK instead of iphoneos SDK
  if (is_ios && defined(dawn_target_platform) && dawn_target_platform == "visionos") {
    args += [ "--visionos" ]
  }

  args += sanitizer_args'''
        new_content = content.replace('  args += sanitizer_args', insertion)
        build_gn.write_text(new_content)
        print("  Patched BUILD.gn")
    else:
        print("  BUILD.gn already patched")

    # 3. Modify build_dawn.py - add iOS/visionOS handling
    build_dawn_py = dawn_dir / "build_dawn.py"
    content = build_dawn_py.read_text()

    if "get_ios_settings" not in content:
        # Update imports
        new_content = content.replace(
            '''from cmake_utils import (add_common_cmake_args, combine_into_library,
                         discover_dependencies, get_cmake_os_cpu,
                         get_windows_settings, quote_if_needed, write_depfile,
                         get_third_party_locations)''',
            '''from cmake_utils import (add_common_cmake_args, combine_into_library,
                         discover_dependencies, get_cmake_os_cpu,
                         get_windows_settings, get_ios_settings,
                         get_visionos_settings, quote_if_needed, write_depfile,
                         get_third_party_locations)'''
        )

        # Add new arguments
        new_content = new_content.replace(
            '''parser.add_argument(
      "--dawn_enable_vulkan", default="false", help="Enable Vulkan backend.")
  args = parser.parse_args()''',
            '''parser.add_argument(
      "--dawn_enable_vulkan", default="false", help="Enable Vulkan backend.")
  parser.add_argument(
      "--ios_simulator", action="store_true",
      help="Building for iOS simulator (uses iphonesimulator SDK)")
  parser.add_argument(
      "--visionos", action="store_true",
      help="Building for visionOS (uses xros SDK instead of iphoneos)")
  args = parser.parse_args()'''
        )

        # Add iOS/visionOS handling
        new_content = new_content.replace(
            '''if target_os == "Darwin" or target_os == "iOS":
    configure_cmd.append(f"-DCMAKE_OSX_ARCHITECTURES={target_cpu}")

  env = os.environ.copy()''',
            '''if target_os == "Darwin" or target_os == "iOS":
    configure_cmd.append(f"-DCMAKE_OSX_ARCHITECTURES={target_cpu}")
    if target_os == "iOS":
      # Get iOS/visionOS SDK settings
      if args.visionos:
        # visionOS: CMake 3.28+ supports CMAKE_SYSTEM_NAME=visionOS
        # We need to override the system name set earlier to use the correct platform
        # Find and replace the CMAKE_SYSTEM_NAME in configure_cmd
        for i, arg in enumerate(configure_cmd):
          if arg.startswith("-DCMAKE_SYSTEM_NAME="):
            configure_cmd[i] = "-DCMAKE_SYSTEM_NAME=visionOS"
            break
        platform_cfgs = get_visionos_settings(target_cpu, is_simulator=args.ios_simulator)
      else:
        # iOS uses iphoneos/iphonesimulator SDK
        platform_cfgs = get_ios_settings(target_cpu, is_simulator=args.ios_simulator)
      configure_cmd += platform_cfgs
      # Disable tint command-line tools for iOS/visionOS (they require MACOSX_BUNDLE config)
      configure_cmd.append("-DTINT_BUILD_CMD_TOOLS=OFF")

  env = os.environ.copy()'''
        )

        build_dawn_py.write_text(new_content)
        print("  Patched build_dawn.py")
    else:
        print("  build_dawn.py already patched")

    # 4. Modify cmake_utils.py - add iOS support and settings functions
    cmake_utils_py = dawn_dir / "cmake_utils.py"
    content = cmake_utils_py.read_text()

    if "get_ios_settings" not in content:
        # Add iOS to get_cmake_os_cpu
        new_content = content.replace(
            '''  if os == "mac":
    target_cpu_map = {
      "arm64": "arm64",
      "x64": "x86_64",
    }
    return "Darwin", target_cpu_map[cpu]

  if os == "win":''',
            '''  if os == "mac":
    target_cpu_map = {
      "arm64": "arm64",
      "x64": "x86_64",
    }
    return "Darwin", target_cpu_map[cpu]

  if os == "ios":
    # iOS uses the same CPU names as Darwin
    target_cpu_map = {
      "arm64": "arm64",
      "x64": "x86_64",
    }
    return "iOS", target_cpu_map[cpu]

  if os == "win":'''
        )

        # Add get_ios_settings and get_visionos_settings functions
        ios_visionos_functions = '''
def get_ios_settings(target_cpu, is_simulator=False):
  """Get CMake settings for iOS cross-compilation.
     Uses xcrun to find the appropriate iOS SDK.

     Args:
       target_cpu: Target CPU architecture (arm64 or x64)
       is_simulator: If True, use simulator SDK regardless of CPU architecture.
                     This is important on Apple Silicon where arm64 is used for
                     both device and simulator builds.
  """
  ios_cfgs = []

  # Use simulator SDK if explicitly requested, otherwise device SDK
  if is_simulator:
    sdk_name = "iphonesimulator"
  else:
    sdk_name = "iphoneos"

  # Get SDK path using xcrun
  try:
    sdk_path = subprocess.check_output(
        ["xcrun", "--sdk", sdk_name, "--show-sdk-path"],
        text=True
    ).strip()
  except subprocess.CalledProcessError:
    print(f"Error: Could not find iOS SDK for {sdk_name}")
    sys.exit(1)

  ios_cfgs.append(f"-DCMAKE_OSX_SYSROOT={sdk_path}")
  # Dawn uses C++ atomic wait/notify_all which requires iOS 14.0+
  ios_cfgs.append("-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0")

  # Cross-compilation hints for pthreads (built-in on iOS)
  # CMake's FindThreads module can't run test programs when cross-compiling,
  # so we need to provide these hints.
  ios_cfgs.append("-DCMAKE_CROSSCOMPILING=YES")
  # Prevent CMake from trying to run test executables during cross-compilation
  ios_cfgs.append("-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY")
  # Thread library hints - pthreads is built into the system on Apple platforms
  ios_cfgs.append("-DTHREADS_PREFER_PTHREAD_FLAG=ON")
  ios_cfgs.append("-DCMAKE_THREAD_LIBS_INIT=-lpthread")
  ios_cfgs.append("-DCMAKE_HAVE_THREADS_LIBRARY=1")
  ios_cfgs.append("-DCMAKE_USE_PTHREADS_INIT=1")
  ios_cfgs.append("-DCMAKE_HAVE_LIBC_PTHREAD=1")

  return ios_cfgs


def get_visionos_settings(target_cpu, is_simulator=False):
  """Get CMake settings for visionOS cross-compilation.
     Uses xcrun to find the appropriate visionOS SDK.

     Since CMake doesn't natively support visionOS, we use CMAKE_SYSTEM_NAME=iOS
     but override the sysroot and add target flags for visionOS (xros).

     Args:
       target_cpu: Target CPU architecture (arm64)
       is_simulator: If True, use simulator SDK
  """
  visionos_cfgs = []

  # Determine SDK and target suffix
  if is_simulator:
    sdk_name = "xrsimulator"
    target_suffix = "-simulator"
  else:
    sdk_name = "xros"
    target_suffix = ""

  # Get SDK path using xcrun
  try:
    sdk_path = subprocess.check_output(
        ["xcrun", "--sdk", sdk_name, "--show-sdk-path"],
        text=True
    ).strip()
  except subprocess.CalledProcessError:
    print(f"Error: Could not find visionOS SDK for {sdk_name}")
    sys.exit(1)

  visionos_cfgs.append(f"-DCMAKE_OSX_SYSROOT={sdk_path}")
  # visionOS minimum deployment target
  visionos_cfgs.append("-DCMAKE_OSX_DEPLOYMENT_TARGET=1.0")
  # Add target triple flags to ensure correct platform metadata in object files
  # This is critical - without it, object files get iOS platform metadata instead of visionOS
  # Include -w to suppress warnings (normally added elsewhere, but we're overriding FLAGS)
  visionos_cfgs.append(f"-DCMAKE_C_FLAGS=-w -target arm64-apple-xros1.0{target_suffix}")
  visionos_cfgs.append(f"-DCMAKE_CXX_FLAGS=-w -target arm64-apple-xros1.0{target_suffix}")
  visionos_cfgs.append(f"-DCMAKE_ASM_FLAGS=-target arm64-apple-xros1.0{target_suffix}")

  # Cross-compilation hints for pthreads (built-in on visionOS)
  visionos_cfgs.append("-DCMAKE_CROSSCOMPILING=YES")
  # Prevent CMake from trying to run test executables during cross-compilation
  visionos_cfgs.append("-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY")
  # Thread library hints - pthreads is built into the system on Apple platforms
  visionos_cfgs.append("-DTHREADS_PREFER_PTHREAD_FLAG=ON")
  visionos_cfgs.append("-DCMAKE_THREAD_LIBS_INIT=-lpthread")
  visionos_cfgs.append("-DCMAKE_HAVE_THREADS_LIBRARY=1")
  visionos_cfgs.append("-DCMAKE_USE_PTHREADS_INIT=1")
  visionos_cfgs.append("-DCMAKE_HAVE_LIBC_PTHREAD=1")

  return visionos_cfgs


def get_windows_settings(args):'''

        new_content = new_content.replace('def get_windows_settings(args):', ios_visionos_functions)

        cmake_utils_py.write_text(new_content)
        print("  Patched cmake_utils.py")
    else:
        print("  cmake_utils.py already patched")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: apply_dawn_ios_visionos.py <skia_src_dir>")
        sys.exit(1)

    skia_dir = Path(sys.argv[1])
    if not skia_dir.exists():
        print(f"Error: Skia directory not found: {skia_dir}")
        sys.exit(1)

    print("Applying Dawn iOS/visionOS patches...")
    if apply_patches(skia_dir):
        print("Done!")
    else:
        print("Failed to apply patches")
        sys.exit(1)
