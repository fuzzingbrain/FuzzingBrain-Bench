#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <webp/mux.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 12) return 0;

    // Try to create mux from raw data (copy_data=1 so we own memory)
    WebPData webp_data;
    webp_data.bytes = data;
    webp_data.size = size;

    WebPMux *mux = WebPMuxCreate(&webp_data, 1 /* copy_data */);
    if (mux == NULL) {
        // If create from data fails, create empty mux and set image
        mux = WebPMuxNew();
        if (mux == NULL) return 0;

        // Try to set the input as an image
        WebPData image_data;
        image_data.bytes = data;
        image_data.size = size;
        WebPMuxSetImage(mux, &image_data, 1);
    }

    // Get canvas size
    int width = 0, height = 0;
    WebPMuxGetCanvasSize(mux, &width, &height);

    // Get feature flags
    uint32_t flags = 0;
    WebPMuxGetFeatures(mux, &flags);

    // Try to get first frame
    WebPMuxFrameInfo frame;
    memset(&frame, 0, sizeof(frame));
    WebPMuxError err = WebPMuxGetFrame(mux, 1, &frame);
    if (err == WEBP_MUX_OK) {
        WebPDataClear(&frame.bitstream);
    }

    // Try to get animation params
    WebPMuxAnimParams anim_params;
    WebPMuxGetAnimationParams(mux, &anim_params);

    // Try to get/set metadata chunks
    WebPData chunk_data;
    if (WebPMuxGetChunk(mux, "EXIF", &chunk_data) == WEBP_MUX_OK) {
        // chunk_data is a reference, don't free
    }
    if (WebPMuxGetChunk(mux, "XMP ", &chunk_data) == WEBP_MUX_OK) {
        // chunk_data is a reference, don't free
    }
    if (WebPMuxGetChunk(mux, "ICCP", &chunk_data) == WEBP_MUX_OK) {
        // chunk_data is a reference, don't free
    }

    // Try to set a custom chunk from part of the fuzz input
    if (size > 20) {
        WebPData custom_chunk;
        custom_chunk.bytes = data + 4;
        custom_chunk.size = size - 4;
        WebPMuxSetChunk(mux, "EXIF", &custom_chunk, 1);
    }

    // Try assembling the mux
    WebPData assembled;
    WebPDataInit(&assembled);
    err = WebPMuxAssemble(mux, &assembled);
    // Always safe to call WebPDataClear per API docs, even on error
    WebPDataClear(&assembled);

    // Get number of chunks of various types
    int num_chunks = 0;
    WebPMuxNumChunks(mux, WEBP_CHUNK_IMAGE, &num_chunks);
    WebPMuxNumChunks(mux, WEBP_CHUNK_ANMF, &num_chunks);

    // Cleanup
    WebPMuxDelete(mux);

    return 0;
}
