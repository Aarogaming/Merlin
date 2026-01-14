from setuptools import setup, find_packages

setup(
    name="merlin-assistant",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "pydantic",
        "requests",
        "psutil",
        "redis",
        "prometheus-fastapi-instrumentator",
        "slowapi",
        "python-jose[cryptography]",
        "passlib[bcrypt]",
        "python-multipart",
        "pyttsx3",
        "SpeechRecognition",
        "loguru",
        "grpcio",
        "grpcio-tools"
    ],
    extras_require={
        "dev": [
            "pytest",
            "black",
            "mypy",
            "httpx"
        ]
    },
    entry_points={
        "console_scripts": [
            "merlin=merlin_cli:main",
        ],
    },
    author="Aaroneous",
    description="A modular personal AI assistant",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/Aarogaming/Merlin",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
)
