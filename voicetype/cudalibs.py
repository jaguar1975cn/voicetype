"""Make the pip-installed CUDA 12 libraries visible to CTranslate2.

CTranslate2 dlopen()s libcublas/libcudnn by soname, which only works if they
are on the loader path. The nvidia-*-cu12 wheels put them inside site-packages
instead. Loading them here with RTLD_GLOBAL puts them in the process before
CTranslate2 asks, so no LD_LIBRARY_PATH is needed at the call site.
"""

import ctypes
import glob
import os
import sys

_SONAMES = (
    "libcublas.so.12",
    "libcublasLt.so.12",
    "libcudnn.so.9",
    "libcudnn_ops.so.9",
    "libcudnn_cnn.so.9",
    "libcudnn_engines_precompiled.so.9",
    "libcudnn_engines_runtime_compiled.so.9",
    "libcudnn_heuristic.so.9",
    "libcudnn_graph.so.9",
    "libcudnn_adv.so.9",
)


def preload() -> list[str]:
    """Load the bundled CUDA libraries. Returns the sonames loaded."""
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.__file__)),
        "site-packages", "nvidia",
    )
    if not os.path.isdir(root):
        root = os.path.join(sys.prefix, "lib",
                            f"python{sys.version_info.major}.{sys.version_info.minor}",
                            "site-packages", "nvidia")
    search = glob.glob(os.path.join(root, "*", "lib"))
    loaded = []
    for soname in _SONAMES:
        for d in search:
            path = os.path.join(d, soname)
            if os.path.exists(path):
                try:
                    ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                    loaded.append(soname)
                except OSError:
                    pass
                break
    return loaded
