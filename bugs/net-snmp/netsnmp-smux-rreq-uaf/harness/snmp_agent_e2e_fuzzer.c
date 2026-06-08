/*
 * LibFuzzer harness for smux_process().
 */
#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>
#include <net-snmp/agent/net-snmp-agent-includes.h>

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

extern int  smux_accept(int);
extern int  smux_process(int);
extern void smux_parse_peer_auth(const char *, char *);
extern void smux_free_peer_auth(void);
extern int  smux_snmp_select_list_add(int);
extern int  smux_snmp_select_list_del(int);

#define FUZZ_SMUX_MAX_PACKET 1500
#define FUZZ_SMUX_MAX_BODY   1490

#define FUZZ_SMUX_OPEN  0x60
#define FUZZ_SMUX_CLOSE 0x41
#define FUZZ_SMUX_RREQ  0x62
#define FUZZ_SMUX_RRSP  0x43
#define FUZZ_SMUX_SOUT  0x44
#define FUZZ_SMUX_TRAP  0xa4

static int
send_all(int fd, const uint8_t *buf, size_t len)
{
    while (len > 0) {
        ssize_t n = send(fd, buf, len, 0);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        if (n == 0)
            return -1;
        buf += (size_t)n;
        len -= (size_t)n;
    }
    return 0;
}

static int
make_loopback_listener(uint16_t *port_out)
{
    int fd;
    int one = 1;
    struct sockaddr_in addr;
    socklen_t addr_len;

    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        return -1;

    (void)setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = 0;

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        return -1;
    }
    if (listen(fd, 1) < 0) {
        close(fd);
        return -1;
    }

    addr_len = sizeof(addr);
    if (getsockname(fd, (struct sockaddr *)&addr, &addr_len) < 0) {
        close(fd);
        return -1;
    }

    *port_out = ntohs(addr.sin_port);
    return fd;
}

static int
connect_loopback(uint16_t port)
{
    int fd;
    struct sockaddr_in addr;

    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        return -1;

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = htons(port);

    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static size_t
build_smux_packet(uint8_t *out, size_t out_size, const uint8_t *data,
                  size_t size)
{
    static const uint8_t types[] = {
        FUZZ_SMUX_RREQ, FUZZ_SMUX_TRAP, FUZZ_SMUX_CLOSE,
        FUZZ_SMUX_OPEN, FUZZ_SMUX_RRSP, FUZZ_SMUX_SOUT
    };
    uint8_t type;
    const uint8_t *body;
    size_t body_len;
    size_t pos = 0;

    if (size == 0 || out_size < 5)
        return 0;

    if ((data[0] & 7) < sizeof(types))
        type = types[data[0] & 7];
    else
        type = data[0];

    body = data + 1;
    body_len = size - 1;
    if (body_len > FUZZ_SMUX_MAX_BODY)
        body_len = FUZZ_SMUX_MAX_BODY;

    out[pos++] = type;
    if (body_len < 128) {
        out[pos++] = (uint8_t)body_len;
    } else if (body_len <= 255) {
        out[pos++] = 0x81;
        out[pos++] = (uint8_t)body_len;
    } else {
        out[pos++] = 0x82;
        out[pos++] = (uint8_t)(body_len >> 8);
        out[pos++] = (uint8_t)body_len;
    }

    if (pos + body_len > out_size)
        return 0;
    memcpy(out + pos, body, body_len);
    return pos + body_len;
}

int
LLVMFuzzerInitialize(int *argc, char ***argv)
{
    (void)argc;
    (void)argv;

    signal(SIGPIPE, SIG_IGN);
    setenv("MIBDIRS", "/tmp/", 1);

    if (getenv("NETSNMP_DEBUGGING") != NULL) {
        snmp_enable_stderrlog();
        snmp_set_do_debugging(1);
        debug_register_tokens("");
    }

    init_agent("snmpd");
    init_snmp("snmpd");
    return 0;
}

int
LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    static const uint8_t open_pdu[] = {
        /* SMUX_OPEN sequence, version 0, OID 1.3.6.1.4.1.8072,
         * description "f", empty password. */
        0x60, 0x11,
        0x02, 0x01, 0x00,
        0x06, 0x07, 0x2b, 0x06, 0x01, 0x04, 0x01, 0xbf, 0x08,
        0x04, 0x01, 0x66,
        0x04, 0x00
    };
    uint8_t packet[FUZZ_SMUX_MAX_PACKET];
    size_t packet_len;
    uint16_t port = 0;
    int listen_fd = -1;
    int client_fd = -1;
    int smux_fd = -1;
    int in_select_list = 0;
    int ret;
    char auth[] = "1.3.6.1.4.1.8072 ";

    smux_free_peer_auth();
    smux_parse_peer_auth("smuxpeer", auth);

    listen_fd = make_loopback_listener(&port);
    if (listen_fd < 0)
        goto out;

    client_fd = connect_loopback(port);
    if (client_fd < 0)
        goto out;

    if (send_all(client_fd, open_pdu, sizeof(open_pdu)) < 0)
        goto out;

    smux_fd = smux_accept(listen_fd);
    if (smux_fd < 0)
        goto out;

    if (smux_snmp_select_list_add(smux_fd))
        in_select_list = 1;

    packet_len = build_smux_packet(packet, sizeof(packet), data, size);
    if (packet_len > 0)
        (void)send_all(client_fd, packet, packet_len);

    /* Make the SMUX fd readable even when there is no fuzz packet, and provide
     * EOF for the cleanup call after a successfully consumed packet. */
    (void)shutdown(client_fd, SHUT_WR);

    ret = smux_process(smux_fd);
    if (ret < 0 && in_select_list) {
        smux_snmp_select_list_del(smux_fd);
        in_select_list = 0;
    }

    errno = 0;
    if (fcntl(smux_fd, F_GETFD) != -1 || errno != EBADF) {
        ret = smux_process(smux_fd);
        if (ret < 0 && in_select_list) {
            smux_snmp_select_list_del(smux_fd);
            in_select_list = 0;
        }
    }

    if (in_select_list) {
        smux_snmp_select_list_del(smux_fd);
        in_select_list = 0;
    }

    errno = 0;
    if (fcntl(smux_fd, F_GETFD) != -1 || errno != EBADF)
        close(smux_fd);
    smux_fd = -1;

out:
    if (client_fd >= 0)
        close(client_fd);
    if (listen_fd >= 0)
        close(listen_fd);
    smux_free_peer_auth();
    return 0;
}
