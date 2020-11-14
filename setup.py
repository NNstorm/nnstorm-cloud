import setuptools

VERSION = "0.4.1"

setuptools.setup(
    name="nnstorm-cloud",
    version=VERSION,
    author="Geza Velkey",
    author_email="geza@nnstorm.com",
    url="https://github.com/NNstorm/nnstorm-cloud",
    description="NNstorm cloud automation",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
