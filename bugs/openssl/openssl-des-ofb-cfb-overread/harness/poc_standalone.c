#include <stdio.h>
#include <string.h>
#include <stdint.h>

typedef unsigned char DES_cblock[8];
typedef uint32_t DES_LONG;

/* Vulnerable pattern from openssl/crypto/des/ofb64ede.c */
static void vulnerable_ofb64(const unsigned char *in,
    unsigned char *out, long length, int *num)
{
    int n = *num;          /* BUG: no range check */
    long l = length;
    DES_cblock d;          /* 8 bytes on stack */
    DES_LONG ti[2];

    memset(d, 0x42, sizeof(d));
    (void)ti;

    while (l--) {
        if (n == 0) {
            memset(d, 0x42, sizeof(d));
        }
        *(out++) = *(in++) ^ d[n];  /* OOB read when n >= 8 */
        n = (n + 1) & 0x07;
    }
    *num = n;
}

int main(void)
{
    unsigned char in[4]  = "AAAA";
    unsigned char out[4] = {0};
    int num = 128;  /* out of range: valid is 0-7 */

    printf("Testing d[128] read (d is 8 bytes)...\n");
    vulnerable_ofb64(in, out, 1, &num);
    return 0;
}
