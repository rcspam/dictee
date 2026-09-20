/* isoc23-shim.c — drop the GLIBC_2.38 requirement of the static ONNX Runtime.
 *
 * glibc 2.38 headers redirect strtol() and friends to __isoc23_strtol() & co
 * (C23 semantics: base 0 or 2 also accepts a "0b" prefix). The prebuilt
 * static libonnxruntime.a that ort-sys bundles was compiled against such
 * headers, so every CPU binary imported GLIBC_2.38 and refused to start on
 * Debian 12 (glibc 2.36), issue #32.
 *
 * Defining the six symbols here, forwarding to the classic functions,
 * satisfies the static library at link time and removes the version
 * dependency. ONNX Runtime only parses decimal option strings, where C23
 * and C17 behave identically.
 *
 * Compiled by build.rs, linked into the binaries only when the `ort-defaults`
 * feature (static ONNX Runtime) is on. The `load-dynamic` CUDA build does
 * not need it. */

#include <stdlib.h>
#include <locale.h>

/* Must not be compiled in C23 mode nor with _GNU_SOURCE: the redirect would
 * then apply to the strtol() calls below and each wrapper would call itself. */
#if (defined(__GLIBC_USE_C2X_STRTOL) && __GLIBC_USE_C2X_STRTOL) \
    || (defined(__GLIBC_USE_C23_STRTOL) && __GLIBC_USE_C23_STRTOL)
#error "isoc23-shim.c must be compiled without the C23 strtol redirect"
#endif

/* Declared by glibc only under _GNU_SOURCE, which we avoid (see above). */
extern long long strtoll_l(const char *, char **, int, locale_t);
extern unsigned long long strtoull_l(const char *, char **, int, locale_t);

long __isoc23_strtol(const char *s, char **end, int base)
{
    return strtol(s, end, base);
}

long long __isoc23_strtoll(const char *s, char **end, int base)
{
    return strtoll(s, end, base);
}

unsigned long __isoc23_strtoul(const char *s, char **end, int base)
{
    return strtoul(s, end, base);
}

unsigned long long __isoc23_strtoull(const char *s, char **end, int base)
{
    return strtoull(s, end, base);
}

long long __isoc23_strtoll_l(const char *s, char **end, int base, locale_t loc)
{
    return strtoll_l(s, end, base, loc);
}

unsigned long long __isoc23_strtoull_l(const char *s, char **end, int base,
                                       locale_t loc)
{
    return strtoull_l(s, end, base, loc);
}
