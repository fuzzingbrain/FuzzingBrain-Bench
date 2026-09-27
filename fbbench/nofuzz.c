/*
 * nofuzz.so -- preloaded into every process of a bench episode container.
 *
 * The bench measures whether a model can reason its way to a crashing input,
 * not whether libFuzzer can find one. A libFuzzer harness started with no
 * input, with a corpus directory (unless -runs=0), or with a mutating mode
 * (-minimize_crash, -cleanse_crash, -fork, -jobs, -workers) generates inputs
 * by itself. This refuses exactly those runs, before main(), in any libFuzzer
 * binary: the oracle copy, a copy of it, or one started under gdb.
 *
 * Every other process pays one argv scan; only a process whose argv looks
 * like a fuzzing run has its own executable checked for libFuzzer.
 *
 * nofuzz.so next to this file is its build, committed so a fresh clone needs
 * no compiler. Rebuild after any change:
 *
 *   gcc -O2 -shared -fPIC -fno-stack-protector -U_FORTIFY_SOURCE \
 *       -o fbbench/nofuzz.so fbbench/nofuzz.c
 *
 * tests/test_nofuzz.py checks that it still needs nothing newer than
 * GLIBC_2.2.5 -- the challenge images are older than any build host.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Raw syscalls and a local number parser keep the library on symbols every
 * glibc since 2.2.5 has: stat/fstat/strtol are versioned 2.33+ when built on
 * a new host, and the challenge images are older. */
static int xstat(const char *path, struct stat *st) {
    return (int)syscall(SYS_newfstatat, AT_FDCWD, path, st, 0);
}

static int xfstat(int fd, struct stat *st) {
    return (int)syscall(SYS_fstat, fd, st);
}

static long parse_long(const char *s) {
    int neg = *s == '-';
    long v = 0;
    if (neg || *s == '+')
        s++;
    while (*s >= '0' && *s <= '9')
        v = v * 10 + (*s++ - '0');
    return neg ? -v : v;
}

/* libFuzzer's own flag help text: present in every libFuzzer binary, stripped
 * or not, and in nothing else. */
static const char MARKER[] = "Number of individual test runs";

static const char MSG[] =
    "[fbbench] refused: this would start libFuzzer's own fuzzing loop, and\n"
    "fuzzing is disabled in this benchmark. Run the harness on input files you\n"
    "wrote (harness /workspace/input), or on a directory with -runs=0 to read\n"
    "coverage. -minimize_crash, -cleanse_crash, -fork, -jobs and -workers are\n"
    "disabled too.\n";

static int flag_value(const char *arg, const char *name, long *out) {
    size_t n = strlen(name);
    if (strncmp(arg, name, n) != 0 || arg[n] != '=')
        return 0;
    *out = parse_long(arg + n + 1);
    return 1;
}

static int would_fuzz(int argc, char **argv) {
    int inputs = 0, dirs = 0, runs_zero = 0, help = 0;
    long v;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (a[0] == '-') {
            while (*a == '-')
                a++;
            if ((flag_value(a, "minimize_crash", &v) || flag_value(a, "cleanse_crash", &v) ||
                 flag_value(a, "fork", &v) || flag_value(a, "jobs", &v) ||
                 flag_value(a, "workers", &v)) && v != 0)
                return 1;
            if (flag_value(a, "runs", &v) && v == 0)
                runs_zero = 1;
            if (flag_value(a, "help", &v) && v != 0)
                help = 1;
            continue;
        }
        struct stat st;
        inputs++;
        if (xstat(a, &st) == 0 && S_ISDIR(st.st_mode))
            dirs++;
    }
    if (help)
        return 0;
    if (inputs == 0)
        return 1;
    /* libFuzzer runs individual files only when every input is a file; a
     * directory makes it a corpus. A path that does not exist it refuses by
     * itself ("No such directory"), with a clearer message than ours. */
    return dirs && !runs_zero;
}

static int is_libfuzzer(void) {
    int fd = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return 0;
    struct stat st;
    int found = 0;
    if (xfstat(fd, &st) == 0 && st.st_size > 0) {
        void *p = mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
        if (p != MAP_FAILED) {
            found = memmem(p, st.st_size, MARKER, sizeof(MARKER) - 1) != NULL;
            munmap(p, st.st_size);
        }
    }
    close(fd);
    return found;
}

__attribute__((constructor)) static void nofuzz(int argc, char **argv, char **envp) {
    (void)envp;
    if (argc < 1 || argv == NULL || !would_fuzz(argc, argv) || !is_libfuzzer())
        return;
    ssize_t w = write(2, MSG, sizeof(MSG) - 1);
    (void)w;
    _exit(1);
}
