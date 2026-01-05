# Set ulimit at the start (if possible)
$(shell ulimit -n 2048)

# Makefile for Skia static libs and example builds

SKIA_BUILDER = python3 build-skia.py

# Build directories
BUILD_DIR = $(shell pwd)/build
EXAMPLE_BUILD_DIR = $(shell pwd)/example/build-mac
WASM_EXAMPLE_BUILD_DIR = $(shell pwd)/example/build-wasm
WASM_GRAPHITE_BUILD_DIR = $(shell pwd)/example/build-wasm-graphite

# Skia paths
SKIA_SRC_DIR = $(BUILD_DIR)/src/skia
EMSDK_PATH = $(SKIA_SRC_DIR)/third_party/externals/emsdk

HTTP_PORT = 8080

.PHONY: skia-mac skia-ios skia-wasm skia-wasm-graphite clean example-mac example-wasm example-wasm-graphite serve-wasm serve-wasm-graphite skia-xcframework skia-spm

# Default target
all: skia-mac example-mac

# Build Skia libraries
skia-mac:
	ulimit -n 2048 && $(SKIA_BUILDER) mac

skia-ios:
	$(SKIA_BUILDER) ios

skia-wasm:
	$(SKIA_BUILDER) wasm -variant cpu

# Build Skia with Graphite/WebGPU for WebAssembly
skia-wasm-graphite:
	$(SKIA_BUILDER) wasm -variant graphite

# Build XCFramework combining iOS and macOS libraries
skia-xcframework:
	$(SKIA_BUILDER) xcframework

# Build example
example-mac: skia-mac
	mkdir -p $(EXAMPLE_BUILD_DIR) && \
	cmake $(shell pwd)/example/CMakeLists.txt -B $(EXAMPLE_BUILD_DIR) -DCMAKE_BUILD_TYPE=Release && \
	cmake --build $(EXAMPLE_BUILD_DIR)

# Build WebAssembly version of example
example-wasm: skia-wasm
	source $(EMSDK_PATH)/emsdk_env.sh && \
	mkdir -p $(WASM_EXAMPLE_BUILD_DIR) && \
	emcmake cmake $(shell pwd)/example/CMakeLists.txt -B $(WASM_EXAMPLE_BUILD_DIR) -DCMAKE_BUILD_TYPE=Release && \
	cmake --build $(WASM_EXAMPLE_BUILD_DIR)

# Serve WebAssembly example
serve-wasm: example-wasm
	source $(EMSDK_PATH)/emsdk_env.sh && \
	cd $(WASM_EXAMPLE_BUILD_DIR) && \
	emrun --port $(HTTP_PORT) --browser chrome example.html

# Build Graphite/WebGPU WebAssembly example
example-wasm-graphite: skia-wasm-graphite
	source $(EMSDK_PATH)/emsdk_env.sh && \
	mkdir -p $(WASM_GRAPHITE_BUILD_DIR) && \
	emcmake cmake $(shell pwd)/example/CMakeLists.txt -B $(WASM_GRAPHITE_BUILD_DIR) -DCMAKE_BUILD_TYPE=Release -DUSE_GRAPHITE=ON && \
	cmake --build $(WASM_GRAPHITE_BUILD_DIR)

# Serve Graphite/WebGPU WebAssembly example
serve-wasm-graphite: example-wasm-graphite
	source $(EMSDK_PATH)/emsdk_env.sh && \
	cd $(WASM_GRAPHITE_BUILD_DIR) && \
	emrun --port $(HTTP_PORT) --browser chrome example.html

# Clean build artifacts
clean:
	rm -rf $(BUILD_DIR)
