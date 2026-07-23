#!/usr/bin/env python3
import argparse, os, re, subprocess
from pathlib import Path

REPO      = Path(__file__).resolve().parent
IMAGE     = os.environ.get("WHEEL_BUILDER_IMAGE", "root-wheel-builder:manylinux_2_28")
VARIANTS  = os.environ.get("WHEEL_VARIANTS",      "max").split()
BUILDS    = [ "cp313-manylinux_x86_64" ]
CACHE     = Path(os.environ.get("WHEEL_CACHE_ROOT", REPO / ".wheel-cache"))
OUT       = Path(os.environ.get("OUTPUT_DIR",       REPO / "wheelhouse"))

def parse_args():
    p = argparse.ArgumentParser(description="Build ROOT wheels via cibuildwheel")
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable ccache (skip mounting/using the ccache and build-dir volumes)",
    )
    return p.parse_args()

def run(*cmd, **kw):
    subprocess.run(cmd, check=True, **kw)

def main():
    args = parse_args()
    use_cache = not args.no_cache

    subprocess.run(["docker", "build", "-t", IMAGE, "-f", REPO / "Dockerfile", REPO], check=True)

    if use_cache:
        subprocess.run(["docker", "run", "--rm", "-v", f"{CACHE}/ccache:/ccache", IMAGE, "ccache", "-z"], check=True)

    for variant in VARIANTS:
        toml = REPO / "wheel_varieties" / variant / "pyproject.toml"
        toml_text = re.sub(r"\.\./\.\./", "", toml.read_text())

        try:
            for build in BUILDS:
                (REPO / "pyproject.toml").write_text(toml_text)
                env = {
                    **os.environ,
                    "CIBW_BUILD":                  build,
                    "CIBW_MANYLINUX_X86_64_IMAGE": IMAGE,
                    "CIBW_BUILD_FRONTEND":         "build",
                    "CIBW_BUILD_VERBOSITY":        "1",
                    "CIBW_CONFIG_SETTINGS":        f"build-dir=/build/{variant}/{{wheel_tag}}",
                }

                if use_cache:
                    env["CIBW_CONTAINER_ENGINE"] = f"docker; create_args: -v {CACHE}/ccache:/ccache -v {CACHE}/build:/build"
                    env["CIBW_ENVIRONMENT"] = (
                        "CCACHE_DIR=/ccache CCACHE_BASEDIR=/project CCACHE_NOHASHDIR=1 "
                        "CCACHE_COMPILERCHECK=content CCACHE_MAXSIZE=5G "
                        "CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime,locale "
                        "CMAKE_C_COMPILER_LAUNCHER=ccache CMAKE_CXX_COMPILER_LAUNCHER=ccache"
                    )
                else:
                    env["CIBW_CONTAINER_ENGINE"] = "docker"

                subprocess.run(["cibuildwheel", "--output-dir", OUT / variant, REPO], check=True, env=env)
        finally:
            (REPO / "pyproject.toml").unlink(missing_ok=True)

    if use_cache:
        subprocess.run(["docker", "run", "--rm", "-v", f"{CACHE}/ccache:/ccache", IMAGE, "ccache", "-s"], check=True)

if __name__ == "__main__":
    main()
