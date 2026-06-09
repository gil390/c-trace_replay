#include "rw_cases.h"

#define RW_SET_VALUE(ctx, value) ((ctx)->value = (value))

int g_rw_counter = 0;
int g_rw_mode = 1;
RwVector *g_rw_escaped_vector = 0;

static void mutate_buffer(uint8_t *buffer, size_t len)
{
    if (len > 0) {
        buffer[0] = (uint8_t)(buffer[0] + 1);
    }
}

static int vector_sum(const RwVector *v)
{
    return (int)(v->x + v->y + v->z);
}

void rw_array_read_write(uint8_t *input, uint8_t *output, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        output[i] = input[i];
    }
}

void rw_array_compound(uint8_t *buffer, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        buffer[i] += 1;
    }
}

void rw_array_increment(uint8_t *buffer, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        buffer[i]++;
    }
}

int rw_pointer_read(const int *src)
{
    return *src;
}

void rw_pointer_write(int *dst)
{
    *dst = 42;
}

void rw_pointer_inout(int *value)
{
    *value += 1;
}

void rw_struct_field_read(RwContext *ctx, int *dst)
{
    *dst = ctx->value;
}

void rw_struct_field_write(RwContext *ctx, int value)
{
    ctx->value = value;
}

void rw_struct_field_inout(RwContext *ctx)
{
    ctx->count += 1;
}

void rw_struct_array_read(RwContext *ctx, uint8_t *output, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        output[i] = ctx->table[i % 16];
    }
}

void rw_global_read(int *dst)
{
    *dst = g_rw_mode;
}

void rw_global_write(int value)
{
    g_rw_counter = value;
}

void rw_global_inout(void)
{
    g_rw_counter++;
}

void rw_call_with_pointer(uint8_t *buffer, size_t len)
{
    mutate_buffer(buffer, len);
}

void rw_conditional_read(uint8_t *input, uint8_t *output, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        if (input[i] != 0) {
            output[i] = input[i];
        }
    }
}

void rw_dynamic_index(uint8_t *input, uint8_t *output, size_t len, size_t offset)
{
    for (size_t i = 0; i < len; i++) {
        output[i] = input[i + offset];
    }
}

void rw_content_dependent_loop(const char *src, char *dst)
{
    while (*src) {
        *dst = *src;
        src++;
        dst++;
    }
    *dst = 0;
}

void rw_typedef_array(rw_byte_t *input, rw_byte_t *output, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        output[i] = input[i];
    }
}

void rw_nested_struct_field(RwOuter *outer, int *dst)
{
    *dst = outer->inner.value;
}

void rw_macro_write(RwContext *ctx, int value)
{
    RW_SET_VALUE(ctx, value);
}

void rw_function_pointer_call(RwCallback callback, uint8_t *buffer, size_t len)
{
    callback(buffer, len);
}

void rw_local_struct_temp(int *dst)
{
    RwVector v = {1.0, 2.0, 3.0};
    v.x += 4.0;
    *dst = (int)(v.x + v.y + v.z);
}

void rw_local_struct_output(double *out)
{
    RwVector v = {1.0, 2.0, 3.0};
    out[0] = v.x;
    out[1] = v.y;
    out[2] = v.z;
}

void rw_local_address_escape_call(int *dst)
{
    RwVector v = {1.0, 2.0, 3.0};
    *dst = vector_sum(&v);
}

void rw_local_address_escape_global(void)
{
    RwVector v = {1.0, 2.0, 3.0};
    g_rw_escaped_vector = &v;
}

RwVector *rw_local_address_escape_return(void)
{
    RwVector v = {1.0, 2.0, 3.0};
    return (RwVector *)(uintptr_t)&v;
}

int rw_local_static_state(int input)
{
    static int acc = 0;
    acc += input;
    return acc;
}
