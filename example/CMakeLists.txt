cmake_minimum_required(VERSION 3.10)
project(SkiaTest)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build options
option(USE_GRAPHITE "Build with Graphite/WebGPU support (WASM only)" OFF)

# Platform-specific settings
if(EMSCRIPTEN)
    # Emscripten-specific settings
    set(CMAKE_EXECUTABLE_SUFFIX ".html")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DSK_TRIVIAL_ABI=[[clang::trivial_abi]]")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS}")

elseif(WIN32)
    # Windows-specific settings
    if(CMAKE_BUILD_TYPE STREQUAL "Debug")
        set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDebug")
        set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /MTd")
    else()
        set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
        set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /MT")
    endif()
    
    if(CMAKE_GENERATOR_PLATFORM STREQUAL "x64")
        set(ARCH_DIR "x64")
    else()
        set(ARCH_DIR "Win32")
    endif()
    
elseif(APPLE)
    # macOS-specific settings
    set(CMAKE_MACOSX_RPATH 1)
    set(CMAKE_BUILD_WITH_INSTALL_RPATH TRUE)
else()
    # Linux-specific settings
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC")
endif()

# Enable Link Time Optimization if supported and not using Emscripten
if(NOT EMSCRIPTEN)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT supported OUTPUT error)
    if(supported)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
    else()
        message(STATUS "IPO is not supported: ${error}")
    endif()
endif()

# Set include and library directories
set(INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/include)

# Configure library paths based on platform and configuration
if(EMSCRIPTEN)
    if(USE_GRAPHITE)
        set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/wasm-graphite/lib/${CMAKE_BUILD_TYPE})
    else()
        set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/wasm-cpu/lib/${CMAKE_BUILD_TYPE})
    endif()
    set(SKIA_LIB ${LIB_DIR}/libskia.a)
elseif(WIN32)
    set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/win/lib/${CMAKE_BUILD_TYPE}/${ARCH_DIR})
    find_library(SKIA_LIB skia PATHS ${LIB_DIR} NO_DEFAULT_PATH REQUIRED)
    
    if(NOT SKIA_LIB)
        message(FATAL_ERROR "Could not find Skia library in ${LIB_DIR}")
    endif()
elseif(APPLE)
    set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/mac/lib/${CMAKE_BUILD_TYPE})
    find_library(SKIA_LIB skia PATHS ${LIB_DIR} NO_DEFAULT_PATH REQUIRED)
else()
    set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/linux/${CMAKE_BUILD_TYPE})
    find_library(SKIA_LIB skia PATHS ${LIB_DIR} NO_DEFAULT_PATH REQUIRED)
endif()

message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "LIB_DIR absolute path: ${LIB_DIR}")
message(STATUS "SKIA_LIB path: ${SKIA_LIB}")

include_directories(${INCLUDE_DIR})

# Select source file based on build variant
if(EMSCRIPTEN AND USE_GRAPHITE)
    add_executable(example main-webgpu.cpp)
    message(STATUS "Building with Graphite/WebGPU support")
else()
    add_executable(example main.cpp)
    message(STATUS "Building CPU-only example")
endif()

# Link libraries
target_link_libraries(example ${SKIA_LIB})

# Platform-specific linking
if(EMSCRIPTEN)
    # Common WASM linker options
    target_link_options(example PRIVATE
        "-sALLOW_MEMORY_GROWTH=1"
        "-sNODEJS_CATCH_EXIT=0"
        "-sDYNAMIC_EXECUTION=0"
        "-sEXPORTED_FUNCTIONS=['_malloc','_free','_main']"
        "-sNO_EXIT_RUNTIME=1"
        "-sINITIAL_MEMORY=128MB"
        "-sWASM=1"
        "-sSTRICT=1"
        "-sERROR_ON_UNDEFINED_SYMBOLS=0"
    )

    if(USE_GRAPHITE)
        # Graphite/WebGPU specific compile and linker options
        target_compile_definitions(example PRIVATE
            SK_GRAPHITE
            SK_DAWN
        )
        # USE_WEBGPU must be set as compile option for headers to be available
        target_compile_options(example PRIVATE
            "-sUSE_WEBGPU=1"
        )
        target_link_options(example PRIVATE
            # WebGPU support
            "-sUSE_WEBGPU=1"
            "-sUSE_WEBGL2=0"
            # ASYNCIFY required for WebGPU async operations
            "-sASYNCIFY"
            "-sASYNCIFY_STACK_SIZE=65536"
            # Closure compiler incompatible with ASYNCIFY
            "--closure=0"
            # Enable assertions for better debugging
            "-sASSERTIONS=1"
            # Use WebGPU shell
            "--shell-file=${CMAKE_CURRENT_SOURCE_DIR}/shell-webgpu.html"
        )
    else()
        # CPU-only specific linker options
        target_link_options(example PRIVATE
            "-sFORCE_FILESYSTEM=1"
            "-sEXPORTED_RUNTIME_METHODS=['FS','ccall','cwrap']"
            "--shell-file=${CMAKE_CURRENT_SOURCE_DIR}/shell.html"
        )
    endif()
elseif(APPLE)
    target_link_libraries(example 
        "-framework CoreFoundation"
        "-framework CoreText"
        "-framework CoreGraphics"
    )
elseif(UNIX AND NOT APPLE)
    target_link_libraries(example 
        pthread
        dl
    )
endif()
