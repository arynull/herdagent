import os
import shutil
import subprocess

PROFILES = ("none", "standard", "strict")


def available() -> bool:
    return shutil.which("bwrap") is not None


def profile_description(profile: str) -> str:
    if profile == "none":
        return "no isolation, backend runs directly on host"
    if profile == "standard":
        return "read-only root with writable cwd and tmp plus isolated pid namespace"
    if profile == "strict":
        return "standard isolation plus no network access"
    raise ValueError(f"unknown sandbox profile: {profile}")


def build_bwrap_args(cwd: str, profile: str) -> list[str]:
    if profile not in PROFILES:
        raise ValueError(f"unknown sandbox profile: {profile}")
    if profile == "none":
        raise ValueError("profile 'none' has no bwrap args")
    if not os.path.isdir(cwd):
        raise ValueError(f"cwd does not exist: {cwd}")
    args = ["bwrap", "--die-with-parent", "--unshare-pid"]
    if profile == "strict":
        args.append("--unshare-net")
    args.extend(
        [
            "--ro-bind",
            "/",
            "/",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--bind",
            cwd,
            cwd,
            "--chdir",
            cwd,
        ]
    )
    return args


def launch(
    cmd: list[str], cwd: str, profile: str = "standard"
) -> tuple[subprocess.Popen, bool]:
    if profile not in PROFILES:
        raise ValueError(f"unknown sandbox profile: {profile}")
    if profile == "none" or not available():
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc, False
    argv = build_bwrap_args(cwd, profile) + list(cmd)
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc, True
