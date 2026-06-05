#include <stdio.h>
#include <stdint.h>
#include "sample.h"

int main(void)
{
    Context ctx = {
        .table = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16},
        .scale = 2
    };
    uint8_t input[8] = {10,20,30,40,50,60,70,80};
    uint8_t output[8] = {0};

    int ret = compute(&ctx, input, output, 8);

    printf("ret=%d\n", ret);
    printf("g_counter=%u\n", g_counter);
    printf("output:");
    for (size_t i=0; i<8; i++) printf(" %u", output[i]);
    printf("\n");
    return 0;
}
