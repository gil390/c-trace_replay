#ifndef RW_CASES_H
#define RW_CASES_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int value;
    int count;
    uint8_t table[16];
} RwContext;

extern int g_rw_counter;
extern int g_rw_mode;

void rw_array_read_write(uint8_t *input, uint8_t *output, size_t len);
void rw_array_compound(uint8_t *buffer, size_t len);
void rw_array_increment(uint8_t *buffer, size_t len);
int rw_pointer_read(const int *src);
void rw_pointer_write(int *dst);
void rw_pointer_inout(int *value);
void rw_struct_field_read(RwContext *ctx, int *dst);
void rw_struct_field_write(RwContext *ctx, int value);
void rw_struct_field_inout(RwContext *ctx);
void rw_struct_array_read(RwContext *ctx, uint8_t *output, size_t len);
void rw_global_read(int *dst);
void rw_global_write(int value);
void rw_global_inout(void);
void rw_call_with_pointer(uint8_t *buffer, size_t len);
void rw_conditional_read(uint8_t *input, uint8_t *output, size_t len);
void rw_dynamic_index(uint8_t *input, uint8_t *output, size_t len, size_t offset);
void rw_content_dependent_loop(const char *src, char *dst);

#endif
