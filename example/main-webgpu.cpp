/**
 * Skia Graphite WebGPU Example
 *
 * This example demonstrates using Skia's Graphite rendering backend with WebGPU
 * in a WebAssembly environment. It requires building Skia with the "graphite"
 * variant and using Emscripten with WebGPU support.
 *
 * Build with: cmake -DUSE_GRAPHITE=ON
 */

#include <emscripten.h>
#include <emscripten/html5.h>
#include <emscripten/html5_webgpu.h>
#include <webgpu/webgpu_cpp.h>

#include "include/core/SkCanvas.h"
#include "include/core/SkColor.h"
#include "include/core/SkColorSpace.h"
#include "include/core/SkFont.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPath.h"
#include "include/core/SkPathBuilder.h"
#include "include/core/SkRRect.h"
#include "include/core/SkSurface.h"
#include "include/effects/SkGradientShader.h"
#include "include/effects/SkGradient.h"

#include "include/gpu/graphite/BackendTexture.h"
#include "include/gpu/graphite/Context.h"
#include "include/gpu/graphite/ContextOptions.h"
#include "include/gpu/graphite/GraphiteTypes.h"
#include "include/gpu/graphite/Recorder.h"
#include "include/gpu/graphite/Recording.h"
#include "include/gpu/graphite/Surface.h"
#include "include/gpu/graphite/dawn/DawnBackendContext.h"
#include "include/gpu/graphite/dawn/DawnTypes.h"
#include "include/gpu/graphite/dawn/DawnUtils.h"

#include <cstdio>
#include <memory>

// Global state
static std::unique_ptr<skgpu::graphite::Context> g_context;
static std::unique_ptr<skgpu::graphite::Recorder> g_recorder;
static wgpu::Device g_device;
static wgpu::Surface g_surface;
static wgpu::SwapChain g_swapChain;
static int g_width = 800;
static int g_height = 600;
static float g_time = 0.0f;

// Async sleep function for yielding to the browser event loop
// This is required when using ASYNCIFY to allow WebGPU operations to complete
EM_ASYNC_JS(void, asyncSleep, (), {
    await new Promise((resolve, _) => {
        setTimeout(resolve, 0);
    });
});

// Tick function for Graphite/Dawn to yield during GPU operations
void webgpuTick(const wgpu::Instance& instance) {
    asyncSleep();
}

// Draw animated content demonstrating Skia Graphite with WebGPU
void drawContent(SkCanvas* canvas) {
    canvas->clear(SK_ColorWHITE);

    // Animated rotation
    canvas->save();
    canvas->translate(g_width / 2.0f, g_height / 2.0f);
    canvas->rotate(g_time * 30.0f);
    canvas->translate(-g_width / 2.0f, -g_height / 2.0f);

    // Draw a gradient background
    SkPaint bgPaint;
    bgPaint.setColor(SkColorSetRGB(230, 235, 255));
    canvas->drawRect(SkRect::MakeWH(g_width, g_height), bgPaint);

    canvas->restore();

    // Draw a simple path using SkPathBuilder
    SkPathBuilder pathBuilder;
    pathBuilder.moveTo(75.0f, 0.0f);
    pathBuilder.lineTo(150.0f, 50.0f);
    pathBuilder.lineTo(150.0f, 100.0f);
    pathBuilder.lineTo(75.0f, 50.0f);
    pathBuilder.close();

    pathBuilder.moveTo(75.0f, 50.0f);
    pathBuilder.lineTo(150.0f, 100.0f);
    pathBuilder.lineTo(150.0f, 150.0f);
    pathBuilder.lineTo(75.0f, 100.0f);
    pathBuilder.close();

    SkPath path = pathBuilder.detach();

    // Draw multiple shapes with animation
    for (int i = 0; i < 3; i++) {
        float offsetX = 100 + i * 200 + sin(g_time + i) * 20;
        float offsetY = 150 + cos(g_time * 0.5f + i) * 30;

        canvas->save();
        canvas->translate(offsetX, offsetY);
        canvas->scale(1.5f, 1.5f);

        // Shadow
        SkPaint shadowPaint;
        shadowPaint.setColor(SkColorSetARGB(60, 0, 0, 0));
        shadowPaint.setAntiAlias(true);
        canvas->save();
        canvas->translate(5, 5);
        canvas->drawPath(path, shadowPaint);
        canvas->restore();

        // Main shape with solid color
        SkPaint shapePaint;
        shapePaint.setAntiAlias(true);
        shapePaint.setColor(SkColorSetRGB(66, 133, 244));  // Blue
        canvas->drawPath(path, shapePaint);

        canvas->restore();
    }

    // Draw animated circles
    for (int i = 0; i < 5; i++) {
        float x = 100 + i * 150;
        float y = 450 + sin(g_time * 2.0f + i * 0.5f) * 50;
        float radius = 30 + sin(g_time * 3.0f + i) * 10;

        SkPaint circlePaint;
        circlePaint.setAntiAlias(true);
        circlePaint.setColor(SkColorSetARGB(
            180,
            (int)(128 + 127 * sin(g_time + i)),
            (int)(128 + 127 * cos(g_time + i * 0.7f)),
            (int)(128 + 127 * sin(g_time * 0.5f + i))
        ));
        canvas->drawCircle(x, y, radius, circlePaint);
    }

    // Draw rounded rectangles
    for (int i = 0; i < 4; i++) {
        float x = 50 + i * 180;
        float y = 300 + cos(g_time + i * 0.8f) * 30;

        SkPaint rectPaint;
        rectPaint.setAntiAlias(true);
        rectPaint.setColor(SkColorSetARGB(200,
            (int)(128 + 127 * cos(g_time * 0.5f + i)),
            (int)(200),
            (int)(128 + 127 * sin(g_time * 0.3f + i))
        ));

        SkRRect rrect = SkRRect::MakeRectXY(
            SkRect::MakeXYWH(x, y, 120, 60),
            15, 15
        );
        canvas->drawRRect(rrect, rectPaint);
    }

    // Draw text
    SkPaint textPaint;
    textPaint.setColor(SK_ColorBLACK);
    textPaint.setAntiAlias(true);

    SkFont font;
    font.setSize(24);

    canvas->drawString("Skia Graphite + WebGPU", 50, 50, font, textPaint);

    char timeStr[64];
    snprintf(timeStr, sizeof(timeStr), "Time: %.1f", g_time);
    canvas->drawString(timeStr, 50, 80, font, textPaint);
}

// Main rendering function called each frame
void render() {
    if (!g_context || !g_recorder || !g_swapChain) {
        printf("Error: Context, recorder, or swapchain not initialized\n");
        return;
    }

    // Get the current swapchain texture
    wgpu::TextureView textureView = g_swapChain.GetCurrentTextureView();
    if (!textureView) {
        printf("Error: Failed to get current texture view\n");
        return;
    }

    // Create TextureInfo for the swapchain texture
    skgpu::graphite::DawnTextureInfo textureInfo(
        /*sampleCount=*/1,
        skgpu::Mipmapped::kNo,
        wgpu::TextureFormat::BGRA8Unorm,
        wgpu::TextureUsage::RenderAttachment,
        wgpu::TextureAspect::All
    );

    // Wrap the texture view in a BackendTexture
    skgpu::graphite::BackendTexture backendTexture =
        skgpu::graphite::BackendTextures::MakeDawn(
            SkISize::Make(g_width, g_height),
            textureInfo,
            textureView.Get()
        );

    if (!backendTexture.isValid()) {
        printf("Error: Failed to create backend texture\n");
        return;
    }

    // Create SkSurface from the backend texture
    sk_sp<SkSurface> surface = SkSurfaces::WrapBackendTexture(
        g_recorder.get(),
        backendTexture,
        kBGRA_8888_SkColorType,
        SkColorSpace::MakeSRGB(),
        nullptr   // surface props
    );

    if (!surface) {
        printf("Error: Failed to create SkSurface\n");
        return;
    }

    // Draw content
    SkCanvas* canvas = surface->getCanvas();
    drawContent(canvas);

    // Snap recording and submit to GPU
    std::unique_ptr<skgpu::graphite::Recording> recording = g_recorder->snap();
    if (recording) {
        skgpu::graphite::InsertRecordingInfo info;
        info.fRecording = recording.get();
        g_context->insertRecording(info);
        g_context->submit(skgpu::graphite::SyncToCpu::kNo);
    }

    // Present the swapchain
    g_swapChain.Present();

    // Update animation time
    g_time += 0.016f;  // Approximately 60fps
}

// Main loop callback for Emscripten
void mainLoop() {
    render();
}

// Initialize WebGPU and Graphite
bool initGraphite() {
    printf("Initializing Graphite with WebGPU...\n");

    // Get the WebGPU device from Emscripten (set up in JavaScript)
    WGPUDevice device = emscripten_webgpu_get_device();
    if (!device) {
        printf("Error: Failed to get WebGPU device from Emscripten\n");
        return false;
    }
    g_device = wgpu::Device::Acquire(device);
    printf("Got WebGPU device\n");

    // Create wgpu::Instance (Emscripten provides a default)
    wgpu::Instance instance = wgpu::CreateInstance();

    // Create surface from the canvas element
    wgpu::SurfaceDescriptorFromCanvasHTMLSelector canvasDesc;
    canvasDesc.selector = "#canvas";

    wgpu::SurfaceDescriptor surfaceDesc;
    surfaceDesc.nextInChain = &canvasDesc;
    g_surface = instance.CreateSurface(&surfaceDesc);
    if (!g_surface) {
        printf("Error: Failed to create WebGPU surface\n");
        return false;
    }
    printf("Created WebGPU surface\n");

    // Create swapchain
    wgpu::SwapChainDescriptor swapChainDesc;
    swapChainDesc.usage = wgpu::TextureUsage::RenderAttachment;
    swapChainDesc.format = wgpu::TextureFormat::BGRA8Unorm;
    swapChainDesc.width = g_width;
    swapChainDesc.height = g_height;
    swapChainDesc.presentMode = wgpu::PresentMode::Fifo;

    g_swapChain = g_device.CreateSwapChain(g_surface, &swapChainDesc);
    if (!g_swapChain) {
        printf("Error: Failed to create swapchain\n");
        return false;
    }
    printf("Created swapchain (%dx%d)\n", g_width, g_height);

    // Create Graphite backend context
    // For WebGPU/Emscripten, we need a tick function to process async operations.
    // The tick function yields to the browser event loop via ASYNCIFY.
    skgpu::graphite::DawnBackendContext backendContext;
    backendContext.fInstance = instance;
    backendContext.fDevice = g_device;
    backendContext.fQueue = g_device.GetQueue();
    backendContext.fTick = webgpuTick;  // Enable async yielding for ASYNCIFY

    // Create Graphite context
    skgpu::graphite::ContextOptions options;
    g_context = skgpu::graphite::ContextFactory::MakeDawn(backendContext, options);
    if (!g_context) {
        printf("Error: Failed to create Graphite context\n");
        return false;
    }
    printf("Created Graphite context\n");

    // Create recorder
    g_recorder = g_context->makeRecorder();
    if (!g_recorder) {
        printf("Error: Failed to create recorder\n");
        return false;
    }
    printf("Created Graphite recorder\n");

    printf("Graphite initialization complete!\n");
    return true;
}

int main() {
    printf("Skia Graphite WebGPU Example\n");
    printf("============================\n");

    // Get canvas size from the DOM element
    double cssWidth, cssHeight;
    emscripten_get_element_css_size("#canvas", &cssWidth, &cssHeight);
    g_width = static_cast<int>(cssWidth);
    g_height = static_cast<int>(cssHeight);
    printf("Canvas size: %dx%d\n", g_width, g_height);

    // Initialize Graphite with WebGPU
    if (!initGraphite()) {
        printf("Failed to initialize Graphite\n");
        return 1;
    }

    // Start the main loop
    printf("Starting main loop...\n");
    emscripten_set_main_loop(mainLoop, 0, true);

    return 0;
}
