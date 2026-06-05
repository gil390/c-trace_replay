#ifndef SAMPLE_H
#define SAMPLE_H

#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint8_t table[16];
    uint8_t scale;
} Context;

extern uint32_t g_counter;
extern int g_mode;

int compute(Context *ctx, uint8_t *input, uint8_t *output, size_t len);

#endif
