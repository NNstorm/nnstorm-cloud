import setuptools

setuptools.setup(
    name="nnstorm-cloud",
    version="0.4.1",
    author="Geza Velkey",
    author_email="geza@nnstorm.com",
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
