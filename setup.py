from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).parent


def read_requirements(path: Path):
    reqs = []
    req_file = ROOT / path
    if not req_file.exists():
        return reqs

    for raw in req_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            nested = line.split(maxsplit=1)[1]
            reqs.extend(read_requirements(Path(nested)))
            continue
        reqs.append(line)
    return reqs


def discover_py_modules():
    modules = []
    for py_file in ROOT.glob("*.py"):
        module_name = py_file.stem
        if module_name == "setup" or module_name.startswith("test_"):
            continue
        modules.append(module_name)
    return sorted(modules)


def discover_packages():
    return sorted(
        set(
            find_packages(
                where=".",
                include=[
                    "core",
                    "core.*",
                    "plugins",
                    "plugins.*",
                ],
            )
        )
    )


base_requirements = read_requirements(Path("requirements.txt"))
dev_requirements = read_requirements(Path("requirements-dev.txt"))
dev_only_requirements = sorted(
    {
        requirement
        for requirement in dev_requirements
        if requirement not in base_requirements
    }
)

plugin_extra_requirements = {
    "web": ["beautifulsoup4"],
    "desktop": ["pyautogui"],
}
plugins_all_requirements = sorted(
    {
        requirement
        for requirements in plugin_extra_requirements.values()
        for requirement in requirements
    }
)

setup(
    name="merlin-assistant",
    version="0.1.0",
    py_modules=discover_py_modules(),
    packages=discover_packages(),
    package_data={
        "plugins": [
            "*/manifest.json",
            "*/aas-plugin.json",
            "*/README.md",
        ]
    },
    include_package_data=True,
    install_requires=base_requirements,
    extras_require={
        "dev": dev_only_requirements,
        **plugin_extra_requirements,
        "plugins-all": plugins_all_requirements,
    },
    entry_points={
        "console_scripts": [
            "merlin=merlin_cli:main",
            "aas=merlin_cli:main",
            "merlin-changelog=merlin_changelog:main",
        ],
    },
    author="Aaroneous",
    description="A modular personal AI assistant",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/Aarogaming/Merlin",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
)
