#include "sample.h"

uint32_t g_counter = 7;
int g_mode = 1;

static uint8_t helper(uint8_t x)
{
    return (uint8_t)(x + 3);
}

float toto(size_t j)
{
    return 12.8 + j;
}

int compute(Context *ctx, uint8_t *input, uint8_t *output, size_t len)
{
    if (!ctx || !input || !output) {
        return -1;
    }

    for (size_t i = 0; i < len; i++) {
        uint8_t local = (uint8_t)(input[i] + ctx->table[i % 16]);
        float f = toto(i);
        if (g_mode) {
            output[i] = (uint8_t)((local + helper(local)) * ctx->scale) + (int)toto(i);
        } else {
            output[i] = local + (int)f;
        }
    }

    g_counter += (uint32_t)len;
    return (int)len;
}
