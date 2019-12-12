#!/usr/bin/env python3

import os
import sys
import shutil
import platform
import argparse
try:
    import lief
except ImportError:
    print("ERROR: lief not installed.")
    print("   $ pip3 install lief --user")
    print("")
    exit(1)

DESCR = """QEMU-AddressSanitizer Builder
Copyright (C) 2019 Andrea Fioraldi <andreafioraldi@gmail.com>
"""

EPILOG="""Note that the ASAN DSO must refer to the host arch (probably x86_64)
and not to the target architecture specified with --arch.
As example, on Ubuntu 18.04, it is:
/usr/lib/llvm-8/lib/clang/8.0.0/lib/linux/libclang_rt.asan-x86_64.so

"""

ARCHS = {
  "x86_64": "x86_64",
  "amd64": "x86_64",
  "x86": "i386",
  "i386": "i386",
}

dir_path = os.path.dirname(os.path.realpath(__file__))

opt = argparse.ArgumentParser(description=DESCR, epilog=EPILOG, formatter_class=argparse.RawTextHelpFormatter)
opt.add_argument("--arch", help="Set target architecture (default x86_64)", action='store', default="x86_64")
opt.add_argument('--asan-dso', help="Path to ASAN DSO", action='store', required=("--clean" not in sys.argv))
opt.add_argument("--clean", help="Clean builded files", action='store_true')
opt.add_argument("--cc", help="C compiler (default clang-8)", action='store', default="clang-8")
opt.add_argument("--cxx", help="C++ compiler (default clang++-8)", action='store', default="clang++-8")

args = opt.parse_args()

host_arch = platform.machine()
output_dso = os.path.join(dir_path, "libclang_rt.asan-%s.so" % host_arch)

def try_remove(path):
    print("Deleting", path)
    try:
        os.remove(path)
    except:
        pass

if args.clean:
    print("Cleaning...")
    try_remove(os.path.join(dir_path, "qasan-qemu"))
    try_remove(os.path.join(dir_path, "libqasan.so"))
    try_remove(os.path.join(dir_path, "libqasan", "libqasan.so"))
    try_remove(output_dso)
    os.system("""cd '%s' ; make clean""" % (os.path.join(dir_path, "qemu")))
    print("Successful clean.")
    print("")
    exit(0)

if args.arch not in ARCHS:
    print("ERROR:", args.arch, "is not a supported architecture.")
    print("Supported architectures are", ", ".join(ARCHS.keys()))
    print("")
    exit(1)

if shutil.which(args.cc) is None:
    print("ERROR:", args.cc, " not found.")
    print("Specify another C compiler with --cc")
    print("")
    exit(1)
if shutil.which(args.cxx) is None:
    print("ERROR:", args.cxx, " not found.")
    print("Specify another C++ compiler with --cxx")
    print("")
    exit(1)

# on Ubuntu 18.04: /usr/lib/llvm-8/lib/clang/8.0.0/lib/linux/libclang_rt.asan-x86_64.so
if not os.path.exists(args.asan_dso):
    print("ERROR:", args.asan_dso, "not found.")
    print("")
    exit(1)

arch = ARCHS[args.arch]

def deintercept(asan_dso, output_dso):
    global arch
    print("Patching", asan_dso)
    lib = lief.parse(asan_dso)

    names = []
    for index, symbol in enumerate(lib.symbols):
        if symbol.type == lief.ELF.SYMBOL_TYPES.FUNC and symbol.name.startswith("__interceptor_"):
            names.append(lib.symbols[index].name[len("__interceptor_"):])

    #names = ["malloc", "calloc", "realloc", "valloc", "pvalloc", "memalign", "posix_memalign", "free"]

    for index, symbol in enumerate(lib.symbols):
        if symbol.type == lief.ELF.SYMBOL_TYPES.FUNC and symbol.binding == lief.ELF.SYMBOL_BINDINGS.WEAK and symbol.name in names:
            print("Renaming ", symbol)
            lib.symbols[index].name = "__qasan_" + symbol.name

    lib.write(output_dso)

deintercept(args.asan_dso, output_dso)

assert ( os.system("""cd '%s' ; ./configure --target-list="%s-linux-user" --disable-system --enable-pie \
  --cc="%s" --cxx="%s" --extra-cflags="-O3 -ggdb" \
  --extra-ldflags="-L %s -lclang_rt.asan-%s -Wl,-rpath,.,-rpath,%s" \
  --enable-linux-user --disable-gtk --disable-sdl --disable-vnc --disable-strip"""
  % (os.path.join(dir_path, "qemu"), arch, args.cc, args.cxx, dir_path, host_arch, dir_path)) == 0 )

assert ( os.system("""cd '%s' ; make -j `nproc`""" % (os.path.join(dir_path, "qemu"))) == 0 )

shutil.copy2(
  os.path.join(dir_path, "qemu", arch + "-linux-user", "qemu-" + arch),
  os.path.join(dir_path, "qasan-qemu")
)

libqasan_cflags = ""
if arch == "i386":
    libqasan_cflags = "-m32"

assert ( os.system("""cd '%s' ; make CC='%s' CFLAGS='%s'"""
  % (os.path.join(dir_path, "libqasan"), args.cc, libqasan_cflags)) == 0 )

shutil.copy2(
  os.path.join(dir_path, "libqasan", "libqasan.so"),
  dir_path
)

print("Successful build.")
print("Test it with ./qasan /bin/ls")
print("")