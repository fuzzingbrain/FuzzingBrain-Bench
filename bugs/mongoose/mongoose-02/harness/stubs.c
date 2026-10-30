#include <stddef.h>

int mg_send()                { return 1; }
void *mg_connect_resolved()  { return 0; }
int mg_multicast_add()       { return 0; }
int mg_open_listener()       { return -1; }
void mg_mgr_poll()           { }
