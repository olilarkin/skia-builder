cmake_minimum_required(VERSION 3.10)
project(SkiaTest)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
    
    # Check for ARM64 on Windows
    if(CMAKE_GENERATOR_PLATFORM STREQUAL "ARM64")
        set(ARCH_DIR "arm64")
    elseif(CMAKE_GENERATOR_PLATFORM STREQUAL "x64")
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
    set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/wasm/lib/${CMAKE_BUILD_TYPE})
    set(SKIA_LIB ${LIB_DIR}/libskia.a)
elseif(WIN32)
    set(LIB_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../build/win/lib/${CMAKE_BUILD_TYPE}/${ARCH_DIR})
    
    # Print debug info
    message(STATUS "Looking for Skia in: ${LIB_DIR}")
    
    # Different library name format based on architecture
    if(ARCH_DIR STREQUAL "arm64")
        find_library(SKIA_LIB NAMES skia.lib PATHS ${LIB_DIR} NO_DEFAULT_PATH REQUIRED)
    else()
        find_library(SKIA_LIB NAMES skia.lib PATHS ${LIB_DIR} NO_DEFAULT_PATH REQUIRED)
    endif()
    
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
message(STATUS "Architecture: ${ARCH_DIR}")
message(STATUS "LIB_DIR absolute path: ${LIB_DIR}")
message(STATUS "SKIA_LIB path: ${SKIA_LIB}")

include_directories(${INCLUDE_DIR})

add_executable(example main.cpp)

# Link libraries
target_link_libraries(example ${SKIA_LIB})

# Platform-specific linking
if(EMSCRIPTEN)
    target_link_options(example PRIVATE
        "-sALLOW_MEMORY_GROWTH=1"
        "-sNODEJS_CATCH_EXIT=0"
        "-sDYNAMIC_EXECUTION=0"
        "-sEXPORTED_FUNCTIONS=['_malloc','_free','_main']"
        "-sNO_EXIT_RUNTIME=1"
        "-sINITIAL_MEMORY=128MB"
        "-sWASM=1"
        "-sSTRICT=1"
        "-f wasm-exceptions"
        "-sERROR_ON_UNDEFINED_SYMBOLS=0"
        "-sFORCE_FILESYSTEM=1"
        "-sEXPORTED_RUNTIME_METHODS=['FS','ccall','cwrap']"
        "--shell-file=${CMAKE_CURRENT_SOURCE_DIR}/shell.html"
    )
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
