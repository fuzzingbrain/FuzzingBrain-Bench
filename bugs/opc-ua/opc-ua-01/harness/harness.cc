#include "custom_memory_manager.h"

#include <open62541/types.h>
#include <open62541/pubsub.h>

/*
** Main entry point. The fuzzer invokes this function with each
** fuzzed input.
*/
extern "C" int
LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if(size < 4)
        return 0;

    /* Set memory limit from last 4 bytes to test OOM handling */
    if(!UA_memoryManager_setLimitFromLast4Bytes(data, size))
        return 0;
    size -= 4;

    /* Create ByteString from fuzz input */
    UA_ByteString buf;
    buf.data = (UA_Byte*)(void*)data;
    buf.length = size;

    /* Decode the NetworkMessage from JSON */
    UA_NetworkMessage nm;
    memset(&nm, 0, sizeof(UA_NetworkMessage));

    UA_StatusCode rv = UA_NetworkMessage_decodeJson(&buf, &nm, NULL, NULL);
    if(rv == UA_STATUSCODE_GOOD) {
        /* If decode succeeded, clean up allocated memory */
        UA_NetworkMessage_clear(&nm);
    }

    return 0;
}
